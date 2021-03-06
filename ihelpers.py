import numpy as np
import pandas as pd
import geopandas as gpd
from pyproj import Proj, transform
from shapely.geometry import Polygon
from bokeh.palettes import brewer
from itertools import product

def xy_to_lonlat(x, y):
    """ Transform x, y coordinates to longitude, latitude.

    params
    ------
    x: x coordinate
    y: y coordinate

    return
    ------
    tuple of (longitude, latitude)
    """

    outProj = Proj("+init=EPSG:4326")
    inProj = Proj("+init=EPSG:28992")
    lon, lat = transform(inProj, outProj, x, y)
    return lon, lat

def convert_polygons_from_xy_to_lonlat(polygons):
    """ Convert an array of shapely.geometry.multipolygon.MultiPolygon objects
        from x, y coordinates to longitude latitude.
    
    params
    ------
    polygons: array or pd.Series of MultiPolygon objects with x, y coordinates.
    
    return
    -------
    array of MultiPolygon objects specified in lon and lat coordinates.
    """
    polygons = pd.Series(polygons)
    return polygons.apply(lambda poly: \
        Polygon([xy_to_lonlat(x, y) for x, y in list(poly[0].exterior.coords)]))

def load_and_preprocess_geodata(path):
    """ Loads geojson and performs simple preprocessing steps.

    params
    ------
    path: the path to the file to load.

    notes
    -----
    Performs the following steps:
        1. convert polygon id to integer
        2. convert polygons from x,y to lon,lat for consistency

    return
    ------ 
    A GeoPandas DataFrame with the loaded and preprocessed data.
    """
    gdflocations = gpd.read_file(path)
    gdflocations["vak"] = gdflocations["vak"].astype(int)
    gdflocations["geometry_lonlat"] = convert_polygons_from_xy_to_lonlat(gdflocations["geometry"])
    return gdflocations


def load_and_preprocess_incidents(path):
    """ Perform preprocessing of datetimes of incidents for convenience
        of plotting.

    params
    ------
    path (str): Path to csv file with incident data.

    notes
    -----
    Performs the following steps:
        1. remove incidents without a polygon (vak) ID
        2. remove incidents outsides the FDAA's service area 
           (since these are not in the geo data)
        3. create ordered pd.Categorical columns for day and 
           month names.

    return
    ------
    DataFrame of incidents with added and adjusted columns
    """

    # load from given path
    incidents = pd.read_csv(path, sep=";", decimal=".",
        usecols=['dim_incident_id','dim_incident_incident_type', 'dim_datum_datum', 
        'dim_datum_jaar', 'dim_datum_maand_nr', 'dim_datum_maand_dag_nr', 
        'dim_datum_week_nr', 'dim_datum_dag_naam_nl','dim_prioriteit_prio', 'dim_tijd_uur',
        'hub_vak_bk', 'hub_vak_id', 'st_x', 'st_y','cluster_naam', 'kazerne_groep'],
        dtype={"dim_tijd_uur": int})

    incidents = incidents[~incidents["hub_vak_bk"].isnull()].copy()
    incidents["hub_vak_bk"] = incidents["hub_vak_bk"].astype(int)
    incidents = incidents[incidents["hub_vak_bk"].astype(str).str[0:2]=="13"]

    # add leading zeros to allow proper sorting
    incidents["hour"] = incidents["dim_tijd_uur"].astype(str).str.zfill(2)
    incidents["day_nr"] = incidents["dim_datum_maand_dag_nr"].astype(str).str.zfill(2)
    incidents["week_nr"] = incidents["dim_datum_week_nr"].astype(str).str.zfill(2)

    # map weekday names to shorts and order them
    incidents["day_name"] = incidents["dim_datum_dag_naam_nl"].map(
        {"Maandag" : "Mon", "Dinsdag" : "Tue", "Woensdag" : "Wed",
        "Donderdag" : "Thu", "Vrijdag" : "Fri", "Zaterdag" : "Sat", "Zondag" : "Sun"})
    incidents["day_name"] = pd.Categorical(incidents["day_name"], ordered=True,
        categories=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
    # same for months
    incidents["month"] = incidents["dim_datum_maand_nr"].astype(int).map(
        {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
         7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"})
    incidents["month"] = pd.Categorical(incidents["month"], ordered=True,
        categories=["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])

    return incidents


def prepare_data_for_geoplot(incidents, vakken):
    """ Preprocess the incident data and geodata for plotting.

    params
    ------
    incidents: DataFrame with the incident data.
    vakken: GeoDataFrame with the polygons representing 
            demand locations.

    notes
    -----
    Performs the following steps:
        1. group the incidents per polygon and count incidents as 
           initial value to plot
        3. merge the polygons to the grouped incident data
        4. remove records with missing polygons to be sure

    return
    ------
    GeoDataFrame with columns ["location_id", "incident_rate", "geometry"]
    """

    # 1 and 2: aggregate and merge
    grouped = incidents.groupby(["hub_vak_bk"])["dim_incident_id"].count().reset_index()
    vakdata = grouped.merge(vakken, left_on="hub_vak_bk", right_on="vak", how="left")

    # 3. to be sure nothing goes wrong later
    vakdata = vakdata[~vakdata["geometry_lonlat"].isnull()].reset_index(drop=True)

    # create and return GeoDataFrame with the relevant data and set the geometry
    vakdata = gpd.GeoDataFrame(vakdata[["hub_vak_bk", "dim_incident_id", "geometry_lonlat"]])
    vakdata.columns = ["location_id", "incident_rate", "geometry"]
    vakdata.set_geometry("geometry", inplace=True)
    vakdata["incident_rate"] = vakdata["incident_rate"].fillna(0)

    return vakdata


def aggregate_data_for_time_series(dfi, agg, pattern, 
                                   group, types, locations):
    """ Aggregate incident data to show the desired pattern.

    Params
    ------
    dfi: DataFrame of incidents.
    agg_col: the column name to aggregate by.
    pattern_col: the column name that represents the pattern 
                 length to be investigated / plotted.
    groupby_col: column to group (color) by.
    types: the incident types that should be included in the plot.

    Return
    ------
    Tuple of the grouped DataFrame and the column name that holds 
    the aggregated values (incident rate).
    """
    
    def add_x_column(df, xcols):
        """ Add a new column consisting of row-wise tuples of
            values from the columns in xcol.

        params
        ------
        df: the DataFrame to add the columns to.
        xcols: the column names of the columns that should 
            make up the new column.

        notes
        -----
        if len(xcols) == 1, then column 'x' is the same as the
        column in xcols.

        return
        ------
        DataFrame with added column named 'x', where the i'th value 
        in df['x'] is a tuple of (df[i, xcols[0]], df[i, xcols[1]], ...).
        """ 

        if len(xcols)>1:
            df['x'] = df.apply(lambda x: tuple(x[col] for col in xcols), axis=1)
        else:
            df['x'] = df[xcols[0]]

        return df.drop(xcols, axis=1)

    # initial columns to use for aggregation
    pattern_mapping = {"Daily": ["dim_datum_datum"],
                       "Weekly": ["dim_datum_jaar", "week_nr"],
                       "Yearly": ["dim_datum_jaar"]}

    agg_mapping = {"Hour": ["hour"],
                   "Day": ["day_name"],
                   "Week": ["week_nr"],
                   "Month": ["month"]}
    
    group_mapping = {"None": None,
                     "Type": ["dim_incident_incident_type"],
                     "Day of Week": ["day_name"],
                     "Year": ["dim_datum_jaar"]}

    pattern_cols = pattern_mapping[pattern]
    agg_cols = agg_mapping[agg]
    groupby_col = group_mapping[group]

    # filter on types and locations
    dfi_filtered = dfi[np.isin(dfi["dim_incident_incident_type"],types)]
    if locations is not None:
        dfi_filtered = dfi_filtered[np.isin(dfi_filtered["hub_vak_bk"], locations)]
    
    # adjust columns if difference in unit is bigger than one
    if (agg == "Hour") & (pattern == "Weekly"):
        agg_cols = ["day_name", "hour"]
    elif (agg == "Hour") & (pattern == "Yearly"):
        agg_cols = ["month", "day_nr", "hour"]
    elif (agg == "Day") & (pattern == "Weekly"):
        pattern_cols = ["dim_datum_jaar", "week_nr"]
    elif (agg == "Day") & (pattern == "Yearly"):
        agg_cols = ["month", "day_nr"]
    else:
        pass

    # wrangle data
    if groupby_col:
        if np.isin(groupby_col, agg_cols+pattern_cols):
            new_index = dfi.groupby(pattern_cols+agg_cols)["dim_incident_id"].count().index
            cols_first_grouping = new_index.names
        else:
            new_index = create_complete_index(dfi, 
                              pattern_cols+agg_cols,
                              "dim_incident_id",
                              list(np.unique(dfi_filtered[groupby_col])))
            cols_first_grouping = pattern_cols+agg_cols+groupby_col
            new_index.names = cols_first_grouping

        grouped = dfi_filtered \
                    .groupby(cols_first_grouping) \
                    ["dim_incident_id"] \
                    .count() \
                    .reindex(new_index, fill_value=0) \
                    .reset_index()

        grouped = grouped \
                    .groupby(agg_cols + groupby_col) \
                    ["dim_incident_id"] \
                    .mean() \
                    .reset_index()

        grouped = order_categoricals(grouped)
        grouped = add_x_column(grouped, agg_cols)

        grouped = grouped \
                    .groupby(groupby_col) \
                    .apply(lambda x: (x["x"].tolist(), 
                                      x["dim_incident_id"].tolist(),
                                      x.name)) \
                    .apply(pd.Series)

        grouped.columns = ["x", "y", "labels"]

        labels = grouped["labels"].tolist()

    else:
        new_index = dfi \
                        .groupby(pattern_cols+agg_cols) \
                        ["dim_incident_id"] \
                        .count() \
                        .index

        grouped = dfi_filtered \
                    .groupby(pattern_cols+agg_cols) \
                    ["dim_incident_id"] \
                    .count() \
                    .reindex(new_index, fill_value=0) \
                    .reset_index()

        grouped = grouped \
                    .groupby(agg_cols) \
                    ["dim_incident_id"] \
                    .mean() \
                    .reset_index()

        grouped = order_categoricals(grouped)
        grouped = add_x_column(grouped, agg_cols)

        grouped.rename(columns={"dim_incident_id": "y"}, inplace=True)

        labels = []

    x = grouped["x"].tolist()
    y = grouped["y"].tolist()

    return x, y, labels

def get_colors(n):
    """ Get list of $n$ distinct color codes.
    
    params
    ------
    n: int
    the number of colors to return.
    
    return
    ------
    list of n Hex color codes.
    """
    if n < 3:
        # minimum 3 colors in the dictionary
        return brewer["Spectral"][3][0:n], n
    else:
        # only 11 colors available in the Spectral palette
        cap = np.min([11, n])
        return brewer["Spectral"][cap], cap

def create_complete_index(data, cols, count_col, factors):
    """ Create MultiIndex from the product of every observed 
        combination of data[cols] with factors.

    params
    ------
    data: DataFrame to create the index from.
    cols: list of column names to include in the index.
    count_col: another column that can be used in the groupby.
    factors: a list of factors to add to the index.

    return
    ------
    a pd.MultiIndex object with all combinations of the *observed*
    tuples (cols[1], cols[2], ...) and all factors.
    """
    new_index = data.groupby(cols)[count_col].count().index
    return pd.MultiIndex.from_tuples(
        [tuple(unit for unit in time)+(type_,)
         for time, type_ in product(*[list(new_index), factors])]
    )

def order_categoricals(df):
    """ Create categoricals and order them logically for 
        day and month names.

    params
    ------
    df: the DataFrame of which columns should be adjusted.

    return
    ------
    a DataFrame similar to df, but where day and month names
    are ordered categoricals and the data is sorted accordingly.
    """ 
    for col in df.columns:
        if col == "day_name":
            df[col] = pd.Categorical(df[col], ordered=True,
                categories=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
        elif col == "month":
            df[col] = pd.Categorical(df[col], ordered=True,
                categories=["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
                            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
        else:
            pass # do nothing
    return df.sort_values(by=list(df.columns))


def filter_on_slider_value(data, time_unit, value):
    """ Filter the data on time. Used to process changes
        in the slider value.

    params
    ------
    data: the pd.DataFrame to filter.
    time_unit: the time unit (column) to perform filtering on.
    value: the value of the time_unit that should be kept.

    return
    ------
    the filtered DataFrame.
    """
    if time_unit=="hour":
        return data[data["hour"]==str(value).zfill(2)]
    elif time_unit=="day":
        mapping = {1:"Mon", 2:"Tue", 3:"Wed", 4:"Thu", 5:"Fri", 6:"Sat", 7:"Sun"}
        return data[data["day_name"]==mapping[value]]
    elif time_unit=="week":
        return data[data["week_nr"]==str(value).zfill(2)]
    elif time_unit=="month":
        return data[data["month"]==str(value).zfill(2)]
    else:
        ValueError("Invalid time_unit: must be one of {'hour', 'day', 'week', 'month'}")
