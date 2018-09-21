import os
os.chdir(b"C:\Users\s100385\Documents\JADS Working Files\Final Project")

import numpy as np
import pandas as pd
import geopandas as gpd

from bokeh.io import output_file, show
from bokeh.models import GeoJSONDataSource, ColumnDataSource, HoverTool, LogColorMapper
from bokeh.models.ranges import FactorRange
from bokeh.models.widgets import Div
from bokeh.plotting import figure, curdoc
from bokeh.palettes import Reds6 as palette
from bokeh.layouts import layout, column, row, widgetbox, gridplot

from ihelpers import preprocess_incidents_for_geoplot, preprocess_incident_datetimes, \
                     aggregate_data_for_time_series, get_colors
from iplotcreators import _create_choropleth_map, _create_time_series, \
                          _create_type_filter, _create_radio_button_group
#from icallbacks import callback_update_time_series

## GLOBAL: LAYOUT AND STYLING ##
LEFT_COLUMN_WIDTH = 700
RIGHT_COLUMN_WIDTH = 500
COLUMN_HEIGHT = 1000

# load and prepare data
dfincident = pd.read_csv(".\Data\incidenten_2008-heden.csv", sep=";", decimal=".",
                         dtype={"dim_tijd_uur": int})
gdflocations = gpd.read_file("./Data/geoData/vakken_dag_ts.geojson")
dfincident = preprocess_incident_datetimes(dfincident)
locdata = preprocess_incidents_for_geoplot(dfincident, gdflocations)
geo_source = GeoJSONDataSource(geojson=locdata.to_json())

# create plots
map_plot = _create_choropleth_map(geo_source, width=LEFT_COLUMN_WIDTH,
                                  height=700)

ts_figure, ts_glyph = _create_time_series(\
                        dfincident, "Hour", "Daily", "None",
                        dfincident["dim_incident_incident_type"].unique(),
                        width=RIGHT_COLUMN_WIDTH, height=350)

# create widgets
pattern_select = _create_radio_button_group(["Daily", "Weekly", "Yearly"])
#pattern_cols = ["dim_datum_datum", "dim_datum_week_nr", "dim_datum_jaar"]

aggregate_select = _create_radio_button_group(["Hour", "Day", "Week", "Month"])
# aggregate_cols = ["dim_tijd_uur", "dim_day_of_week",
#                   "dim_datum_week_nr", "dim_datum_maand_nr"]

groupby_select = _create_radio_button_group(["Type", "Day of Week", "Year", "None"])
# groupby_cols = ["dim_incident_incident_type", "dim_day_of_week", "dim_datum_jaar", None]

incident_types = dfincident["dim_incident_incident_type"].astype(str).unique()
type_filter = _create_type_filter(incident_types)

# headers
pattern_head = Div(text="Pattern:")
agg_head = Div(text="Aggregate by:")
groupby_head = Div(text="Group by:")
type_head = Div(text="Select incident types:")

## add callbacks
def callback_update_time_series(attr, old, new):
    """ Updates the time series plot when filters have changed.

    params
    ------
    attr: the attribute that changed.
    old: old value of 'attr'.
    new: new value of 'attr'.

    notes
    -----
    The callback input (attr, old, new) is not used in order 
    to make the function callable when different filters change.
    """
    agg_by = aggregate_select.labels[aggregate_select.active]
    pattern = pattern_select.labels[pattern_select.active]
    group_by = groupby_select.labels[groupby_select.active]
    types = incident_types[type_filter.active]

    data, x_column, y_column = aggregate_data_for_time_series(dfincident, agg_by, 
                                                              pattern, group_by,
                                                              types)
    # debug
    ## TODO: condition on type of data[x_column], flatten (since it contains lists)
    # and get unique values
    print(type(data[x_column]))
    print(type(data[x_column][0]))
    print(type(data[x_column][0][0]))
    if hasattr(data[x_column][0], "__iter__"):
        print("round 1")
        if isinstance(data[x_column][0][0], str):
            print("so, we here now")
            print(np.unique([val for lst in data[x_column] for val in lst]))
            ts_figure.x_range = FactorRange(factors=\
                np.unique([val for lst in data[x_column] for val in lst]))
            print("range successful?")
            
    if group_by != "None":
        colors, ngroups = get_colors(len(data))
        ts_glyph.data_source.data = {"xs": data[x_column].tolist()[0:ngroups],
                                     "ys": data[y_column].tolist()[0:ngroups],
                                     "cs": colors,
                                     "label": data["label"].tolist()[0:ngroups]}
    else:
        ts_glyph.data_source.data = {"xs": [data[x_column].tolist()],
                                     "ys": [data[y_column].tolist()],
                                     "cs": ["green"],
                                     "label": ["avg incidents"]}

pattern_select.on_change('active', callback_update_time_series)
aggregate_select.on_change('active', callback_update_time_series)
groupby_select.on_change('active', callback_update_time_series)
type_filter.on_change('active', callback_update_time_series)
## end callbacks

# create layout of application
radios_widgetbox = widgetbox(children=[pattern_head, pattern_select, 
                          agg_head, aggregate_select,
                          groupby_head, groupby_select])
type_widgetbox = widgetbox(children=[type_head, type_filter])
widgets = row(children=[type_widgetbox, radios_widgetbox])
main_left = column(children=[map_plot], width=LEFT_COLUMN_WIDTH, 
                   height=COLUMN_HEIGHT)
main_right = column(children=[ts_figure, widgets], 
                    width=RIGHT_COLUMN_WIDTH, height=COLUMN_HEIGHT)
root = layout([[main_left, main_right]])
curdoc().add_root(root)

