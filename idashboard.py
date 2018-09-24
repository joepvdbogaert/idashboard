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

from ihelpers import preprocess_incidents_for_geoplot, load_and_preprocess_incidents, \
                     aggregate_data_for_time_series, get_colors
from iplotcreators import _create_choropleth_map, _create_time_series, \
                          _create_type_filter, _create_radio_button_group
#from icallbacks import callback_update_time_series

## GLOBAL: LAYOUT AND STYLING ##
LEFT_COLUMN_WIDTH = 700
RIGHT_COLUMN_WIDTH = 600
COLUMN_HEIGHT = 1000

# load and prepare data
gdflocations = gpd.read_file("./Data/geoData/vakken_dag_ts.geojson")
dfincident = load_and_preprocess_incidents(".\Data\incidenten_2008-heden.csv")
locdata = preprocess_incidents_for_geoplot(dfincident, gdflocations)
geo_source = GeoJSONDataSource(geojson=locdata.to_json())

feasible_combos = {"Daily": {"agg": ["Hour"],
                             "group": ["Type", "Day of Week", "Year", "None"]},
                   "Weekly": {"agg": ["Hour", "Day"],
                             "group": ["Type", "Year", "None"]},
                   "Yearly": {"agg": ["Day", "Week", "Month"],
                              "group": ["Type", "Year", "None"]}}

# create plots
map_figure, map_glyph = _create_choropleth_map(geo_source, width=LEFT_COLUMN_WIDTH,
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
def update_time_series(filter_, attr, old, new):
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

    def feasible_selection(agg, pat, group):
        """ Check if current selection is feasible """

        if (np.isin(agg, feasible_combos[pat]["agg"])) & \
           (np.isin(group, feasible_combos[pat]["group"])):
           return True
        else:
            return False

    agg_by = aggregate_select.labels[aggregate_select.active]
    pattern = pattern_select.labels[pattern_select.active]
    group_by = groupby_select.labels[groupby_select.active]
    types = incident_types[type_filter.active]

    if not feasible_selection(agg_by, pattern, group_by):
        
        # ignore or adjust requested update
        if filter_ == "agg":
            aggregate_select.active = old
        elif filter_ == "pattern":
            # adjust the aggregation and groupby
            # to make sure they're feasible
            aggregate_select.active = \
                aggregate_select.labels.index(feasible_combos[pattern]["agg"][0])
            groupby_select.active = 3
        elif filter_ == "group":
            groupby_select.active = old

    
    # filter on location if map selection is made
    if len(geo_source.selected.indices)>0:
        loc_indices = geo_source.selected.indices
        loc_ids = [locdata.iloc[int(idx)]["location_id"] for idx in loc_indices]
        incidents = dfincident[np.isin(dfincident["hub_vak_bk"], loc_ids)]
    else:
        incidents = dfincident

    # aggregate and prepare data
    x, y, labels = aggregate_data_for_time_series(incidents, agg_by, 
                                                  pattern, group_by,
                                                  types)

    if group_by != "None":
        colors, ngroups = get_colors(len(labels))
        ts_glyph.data_source.data = {"xs": x[0:ngroups],
                                     "ys": y[0:ngroups],
                                     "cs": colors,
                                     "label": labels[0:ngroups]}
        ts_figure.x_range.factors = x[0]

    else:
        ts_glyph.data_source.data = {"xs": [x],
                                     "ys": [y],
                                     "cs": ["green"],
                                     "label": ["avg incident count"]}
        ts_figure.x_range.factors = x

# wrappers for update to include the changed filter
def callback_pattern_selection(attr, old, new):
    update_time_series("pattern", attr, old, new)

def callback_aggregation_selection(attr, old, new):
    update_time_series("agg", attr, old, new)

def callback_groupby_selection(attr, old, new):
    update_time_series("group", attr, old, new)

def callback_type_filter(attr, old, new):
    update_time_series("types", attr, old, new)

def callback_map_selection(attr, old, new):
    update_time_series("map", attr, old, new)

    

pattern_select.on_change('active', callback_pattern_selection)
aggregate_select.on_change('active', callback_aggregation_selection)
groupby_select.on_change('active', callback_groupby_selection)
type_filter.on_change('active', callback_type_filter)
geo_source.on_change('selected', callback_map_selection)
## end callbacks

# create layout of application
radios_widgetbox = widgetbox(children=[pattern_head, pattern_select, 
                          agg_head, aggregate_select,
                          groupby_head, groupby_select])
type_widgetbox = widgetbox(children=[type_head, type_filter])
widgets = row(children=[type_widgetbox, radios_widgetbox])
main_left = column(children=[map_figure], width=LEFT_COLUMN_WIDTH, 
                   height=COLUMN_HEIGHT)
main_right = column(children=[ts_figure, widgets], 
                    width=RIGHT_COLUMN_WIDTH, height=COLUMN_HEIGHT)
root = layout([[main_left, main_right]])
curdoc().add_root(root)

