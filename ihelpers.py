import numpy as np
import pandas as pd
import geopandas as gpd
from pyproj import Proj, transform
from shapely.geometry import Polygon
from bokeh.palettes import brewer

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

def preprocess_incidents_for_geoplot(incidents, vakken):
    """ Preprocess the incident data and geodata for plotting.

    params
    ------
    incidents: DataFrame with the incident data.
    vakken: GeoDataFrame with the polygons representing 
            demand locations.

    notes
    -----
    Performs the following steps:
        1. remove incidents without a polygon (vak) ID
        2. convert polygon id to integer
        3. remove incidents outsides the FDAA's service area 
           (since these are not in the geo data)
        4. convert polygons from x,y to lon,lat for consistency
        5. group the incidents per polygon and count incidents as 
           initial value to plot
        6. merge the polygons to the grouped incident data
        7. remove records with missing polygons to be sure

    return
    ------
    GeoDataFrame with columns ["location_id", "incident_rate", "geometry"]
    """

    # step 1 to 4
    incidents = incidents[~incidents["hub_vak_bk"].isnull()].copy()
    incidents["hub_vak_bk"] = incidents["hub_vak_bk"].astype(int)
    vakken["vak"] = vakken["vak"].astype(int)
    incidents = incidents[incidents["hub_vak_bk"].astype(str).str[0:2]=="13"]
    vakken["geometry_lonlat"] = convert_polygons_from_xy_to_lonlat(vakken["geometry"])

    # 5 and 6: aggregate and merge
    grouped = incidents.groupby(["hub_vak_bk"])["dim_incident_id"].count().reset_index()
    vakdata = grouped.merge(vakken, left_on="hub_vak_bk", right_on="vak", how="left")

    # 7. to be sure nothing goes wrong later
    vakdata = vakdata[~vakdata["geometry_lonlat"].isnull()].reset_index(drop=True)

    # create and returnGeoDataFrame with the relevant data and set the geometry
    vakdata = gpd.GeoDataFrame(vakdata[["hub_vak_bk", "dim_incident_id", "geometry_lonlat"]])
    vakdata.columns = ["location_id", "incident_rate", "geometry"]
    vakdata.set_geometry("geometry", inplace=True)

    return vakdata

def aggregate_data_for_time_series(dfi, agg, pattern, 
                                   group, types):
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
    
    # initial columns to use for aggregation
    pattern_mapping = {"Daily": "dim_datum_datum",
                       "Weekly": "dim_year_and_weeknr",
                       "Yearly": "dim_datum_jaar"}

    agg_mapping = {"Hour": "dim_tijd_uur",
                   "Day": "dim_day_of_week",
                   "Week": "dim_datum_week_nr",
                   "Month": "dim_datum_maand_nr"}
    
    group_mapping = {"None": None,
                     "Type": "dim_incident_incident_type",
                     "Day of Week": "dim_day_of_week",
                     "Year": "dim_datum_jaar"}

    pattern_col = pattern_mapping[pattern]
    agg_col = agg_mapping[agg]
    groupby_col = group_mapping[group]

    # filter types
    dfi_filtered = dfi[np.isin(dfi["dim_incident_incident_type"],types)]
    
    # adjust columns if difference in unit is bigger than one
    if (agg == "Hour") & (pattern == "Weekly"):
        agg_col = "dim_weekday_and_hour"
    elif (agg == "Hour") & (pattern == "Yearly"):
        agg_col = "dim_month_daynr_hour"
    elif (agg == "Day") & (pattern == "Weekly"):
        pattern_col = "dim_year_and_weeknr"
    elif (agg == "Day") & (pattern == "Yearly"):
        agg_col = "dim_month_and_daynr"
    else:
        pass

    # wrangle data
    if groupby_col:
        grouped = dfi_filtered \
                    .groupby([agg_col, pattern_col, groupby_col]) \
                    ["dim_incident_id"] \
                    .count() \
                    .reset_index()

        grouped = grouped \
                    .groupby([agg_col, groupby_col]) \
                    ["dim_incident_id"] \
                    .mean() \
                    .reset_index()

        count_col = "number of incidents"
        grouped.rename(columns={"dim_incident_id" : count_col}, inplace=True)
        data = grouped.groupby(groupby_col) \
                .apply(lambda x: (x[agg_col].tolist(), x[count_col].tolist(), x.name)) \
                .apply(pd.Series)
        data.columns = [agg_col, count_col, "label"]
        data[agg_col] = data[agg_col].astype(str)
    else:
        grouped = dfi_filtered \
                    .groupby([agg_col, pattern_col]) \
                    ["dim_incident_id"] \
                    .count() \
                    .reset_index()

        grouped = grouped \
                    .groupby([agg_col]) \
                    ["dim_incident_id"] \
                    .mean() \
                    .reset_index()

        count_col = "number of incidents"
        data = grouped.rename(columns={"dim_incident_id" : count_col})
        data[agg_col] = data[agg_col].astype(str)

    return data, agg_col, count_col

def preprocess_incident_datetimes(incidents):
    """ Perform preprocessing of datetimes of incidents for convenience
        of plotting.

    params
    ------
    incidents: DataFrame containing the incident data.

    return
    ------
    DataFrame of incidents with added and adjusted columns
    """

    # add leading zeros
    incidents["dim_tijd_uur"] = incidents["dim_tijd_uur"].astype(str).str.zfill(2)
    # map weekday names to numbers
    incidents["dim_day_of_week"] = incidents["dim_datum_dag_naam_nl"].map(
                                        {"Maandag" : 1, "Dinsdag" : 2, "Woensdag" : 3, 
                                        "Donderdag" : 4, "Vrijdag" : 5, "Zaterdag" : 6,
                                        "Zondag" : 7}
                                        )

    # create indicator for day-of-week + hour-of-day
    incidents["dim_weekday_and_hour"] = "D" + incidents["dim_day_of_week"].astype(str) + \
                                        " H" + incidents["dim_tijd_uur"].astype(str)
    incidents["dim_month_and_daynr"] = "M" + incidents["dim_datum_maand_nr"].astype(str) + \
                                       " D" + incidents["dim_datum_maand_dag_nr"].astype(str)
    incidents["dim_month_daynr_hour"] = "M" + incidents["dim_datum_maand_nr"].astype(str) + \
                                        " D" + incidents["dim_datum_maand_dag_nr"].astype(str) + \
                                        " H"+ incidents["dim_tijd_uur"].astype(str)
    incidents["dim_year_and_weeknr"] = incidents["dim_datum_jaar"].astype(str) + \
                                        " W" + incidents["dim_datum_week_nr"].astype(str)

    return incidents

def get_colors(n):
    """ Get list of n distinct color codes.
    
    params
    ------
    n: int
    the number of colors to return.
    
    return
    ------
    list of n Hex color codes.
    """
    cap = np.min([11, n])
    # only 12 colors available in the Spectral palette
    # (besides, more than that would be unreadable in the plot anyways.)
    return brewer["Spectral"][cap], cap