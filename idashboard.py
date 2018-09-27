import os
os.chdir(b"C:\Users\s100385\Documents\JADS Working Files\Final Project")

from threading import Timer

import numpy as np
import pandas as pd
import geopandas as gpd

from bokeh.io import output_file, show
from bokeh.models import GeoJSONDataSource, ColumnDataSource, HoverTool, LogColorMapper
from bokeh.models.ranges import FactorRange, DataRange1d, Range1d
from bokeh.models.widgets import Div, MultiSelect, Button, Toggle
from bokeh.models.callbacks import CustomJS
from bokeh.plotting import figure, curdoc
from bokeh.palettes import Reds6 as palette
from bokeh.layouts import layout, column, row, widgetbox, gridplot

from ihelpers import prepare_data_for_geoplot, load_and_preprocess_incidents, \
                     aggregate_data_for_time_series, get_colors, load_and_preprocess_geodata, \
                     filter_on_slider_value
from iplotcreators import _create_choropleth_map, _create_time_series, \
                          _create_type_filter, _create_radio_button_group, create_slider, \
                          _get_slider_params
#from icallbacks import callback_update_time_series

## GLOBAL: LAYOUT AND STYLING ##
LEFT_COLUMN_WIDTH = 700
RIGHT_COLUMN_WIDTH = 700
COLUMN_HEIGHT = 1000

# load and prepare data
gdflocations = load_and_preprocess_geodata("./Data/geoData/vakken_dag_ts.geojson")
dfincident = load_and_preprocess_incidents(".\Data\incidenten_2008-heden.csv")
locdata = prepare_data_for_geoplot(dfincident, gdflocations)
geo_source = GeoJSONDataSource(geojson=locdata.to_json())

feasible_combos = {"Daily": {"agg": ["Hour"],
                             "group": ["Type", "Day of Week", "Year", "None"]},
                   "Weekly": {"agg": ["Hour", "Day"],
                             "group": ["Type", "Year", "None"]},
                   "Yearly": {"agg": ["Day", "Week", "Month"],
                              "group": ["Type", "Year", "None"]}}

slider_time_unit_mapping = {0: "hour",
                            1: "day",
                            2: "month"}
# create plots
map_figure, map_glyph = _create_choropleth_map(geo_source, width=LEFT_COLUMN_WIDTH,
                                               height=700)

ts_figure, ts_glyph = _create_time_series(\
                        dfincident, "Hour", "Daily", "None",
                        dfincident["dim_incident_incident_type"].unique(),
                        width=600, height=350)

# create widgets
slider_time_unit = "hour"
time_slider = create_slider(slider_time_unit)
slider_active_toggle = Toggle(label="slider not active", active=False,
                              button_type="default", width=150)
pattern_select = _create_radio_button_group(["Daily", "Weekly", "Yearly"])
aggregate_select = _create_radio_button_group(["Hour", "Day", "Week", "Month"])
groupby_select = _create_radio_button_group(["None", "Type", "Day of Week", "Year"])
incident_types = dfincident["dim_incident_incident_type"].astype(str).unique()
#type_filter = _create_type_filter(incident_types)
type_filter = MultiSelect(title="Incident Types:", value=list(incident_types),
                          options=[(t, t) for t in incident_types],
                          size=10)
select_all_types_button = Button(label="Select all", button_type="primary",
                                 width=150)

# headers
status_available_style = {"font-size": "8pt", "color": "green"}
status_unavailable_style = {"font-size": "8pt", "color": "red"}
status = Div(text="""<i>Status: at your service</i>""", style={"font-size": "8pt", "color": "green"})
pattern_head = Div(text="Pattern:")
agg_head = Div(text="Aggregate by:")
groupby_head = Div(text="Group by:")

## add callbacks
def update_time_series(filter_, attr, old, new):
    """ Updates the time series plot when filters have changed.

    params
    ------
    filter_: identifier for the filter that has been changed.
             One of {'agg', 'pattern', 'group', 'types'}.
    attr: the attribute that changed.
    old: old value of 'attr'.
    new: new value of 'attr'.

    notes
    -----
    The callback input (attr, old, new) is not used in order 
    to make the function callable from different filters changes.
    """
    status.style = status_unavailable_style
    status.text = "<i>Status: calculating...</i>"
    
    agg_by = aggregate_select.labels[aggregate_select.active]
    pattern = pattern_select.labels[pattern_select.active]
    group_by = groupby_select.labels[groupby_select.active]
    types = type_filter.value

    # check for feasibility and possibly cancel update
    perform_update = True
    if not np.isin(agg_by, feasible_combos[pattern]["agg"]):
        if filter_ == "agg":
            aggregate_select.active = old
            perform_update = False
        else:
            aggregate_select.active = \
                aggregate_select.labels.index(feasible_combos[pattern]["agg"][0])
    if not np.isin(group_by, feasible_combos[pattern]["group"]):
        if filter_ == "group":
            groupby_select.active = old
            perform_update = False
        else:
            groupby_select.active = 3 # No groupby

    if perform_update:
        # filter on location if map selection is made
        if len(geo_source.selected.indices)>0:
            loc_indices = geo_source.selected.indices
            loc_ids = [locdata.iloc[int(idx)]["location_id"] for idx in loc_indices]
            #incidents = dfincident[np.isin(dfincident["hub_vak_bk"], loc_ids)]
        else:
            loc_ids=None
            #incidents = dfincident

        # aggregate and prepare data
        x, y, labels = aggregate_data_for_time_series(dfincident, agg_by, 
                                                      pattern, group_by,
                                                      types, loc_ids)

        if group_by != "None":
            colors, ngroups = get_colors(len(labels))
            #ts_figure.y_range.start = 0.9*np.min(y)
            #ts_figure.y_range.end = 1.1*np.max(y)+1
            
            ts_glyph.data_source.data = {"xs": x[0:ngroups],
                                         "ys": y[0:ngroups],
                                         "cs": colors,
                                         "label": labels[0:ngroups]}
            ts_figure.x_range.factors = x[0]            
        else:
            #ts_figure.y_range.start = 0.9*np.min(y)
            #ts_figure.y_range.end = 1.1*np.max(y)
            ts_glyph.data_source.data = {"xs": [x],
                                         "ys": [y],
                                         "cs": ["green"],
                                         "label": ["avg incident count"]}
            ts_figure.x_range.factors = x

    else:
        print("Update cancelled due to impossible filter combination.")

    status.style = status_available_style
    status.text = "<i>Status: at your service</i>"

def update_map(filtered_incidents):
    locdata = prepare_data_for_geoplot(filtered_incidents, gdflocations)
    # udpate source of map plot
    map_glyph.data_source.geojson = locdata.to_json()

def update_time_slider(pattern):
    slider_time_unit = slider_time_unit_mapping[pattern]
    start, end, value, step, title = _get_slider_params(slider_time_unit)
    time_slider.start = start
    time_slider.end = end
    time_slider.value = value
    time_slider.step = step
    time_slider.title = title

# Javascript callback that plays the animation
callback_play = CustomJS(args=dict(slider=time_slider,
                                   active_button=slider_active_toggle),
                         code="""

// set slider to active
active_button.active = true;

// start or stop playing
var a = cb_obj.active;
if(a==true){
    cb_obj.label = "STOP";
    cb_obj.button_type = "danger";
    mytimer = setInterval(add_one, 1000);             
} else {
    cb_obj.label = "PLAY";
    cb_obj.button_type = "primary";
    clearInterval(mytimer);
}

// function that loops the value of the slider
function add_one() {
    if(slider.value+1 <= slider.end){
        slider.value++;
    } else {
        slider.value = slider.start;
    }
}
""")

# wrappers for update to include the changed filter
def callback_pattern_selection(attr, old, new):
    update_time_series("pattern", attr, old, new)
    update_time_slider(new)

def callback_aggregation_selection(attr, old, new):
    update_time_series("agg", attr, old, new)

def callback_groupby_selection(attr, old, new):
    update_time_series("group", attr, old, new)

def callback_type_filter(attr, old, new):
    update_time_series("types", attr, old, new)
    filtered_data = filter_on_slider_value(dfincident, slider_time_unit, time_slider.value)
    filtered_data = filtered_data[np.isin(filtered_data["dim_incident_incident_type"], new)]
    update_map(filtered_data)

def callback_map_selection(attr, old, new):
    update_time_series("map", attr, old, new)    

def callback_select_all_types():
    type_filter.value = list(incident_types)

def callback_time_slider(attr, old, new):
    if slider_active_toggle.active:
        filtered_data = filter_on_slider_value(dfincident, slider_time_unit, new)
        filtered_data = filtered_data[np.isin(filtered_data["dim_incident_incident_type"], 
                                              type_filter.value)]
        update_map(filtered_data)

def callback_toggle_slider_activity(active):
    
    if active==True:
        slider_value = time_slider.value
        callback_time_slider('value', slider_value, slider_value)
        slider_active_toggle.label = "slider active"
        slider_active_toggle.button_type = "warning"
    
    if active==False:
        filtered_data = dfincident[np.isin(dfincident["dim_incident_incident_type"], 
                                           type_filter.value)]
        update_map(filtered_data)
        slider_active_toggle.label = "slider not active"
        slider_active_toggle.button_type = "default"

# assign callbacks
play_button = Toggle(label="PLAY", button_type="primary", width=100, callback=callback_play)
time_slider.on_change('value', callback_time_slider)
slider_active_toggle.on_click(callback_toggle_slider_activity)
pattern_select.on_change('active', callback_pattern_selection)
aggregate_select.on_change('active', callback_aggregation_selection)
groupby_select.on_change('active', callback_groupby_selection)
type_filter.on_change('value', callback_type_filter)
geo_source.on_change('selected', callback_map_selection)
select_all_types_button.on_click(callback_select_all_types)
## end callbacks

# create layout of application
radios_widgetbox = widgetbox(children=[status, pattern_head, pattern_select, 
                                       agg_head, aggregate_select,
                                       groupby_head, groupby_select])
type_widgetbox = column(children=[type_filter, select_all_types_button])

widgets = column(children=[row(children=[time_slider, play_button, slider_active_toggle]),
                           row(children=[type_widgetbox, radios_widgetbox])])

main_left = column(children=[map_figure], width=LEFT_COLUMN_WIDTH, 
                   height=COLUMN_HEIGHT)
main_right = column(children=[ts_figure, widgets], 
                    width=RIGHT_COLUMN_WIDTH, height=COLUMN_HEIGHT)
root = layout([[main_left, main_right]])
curdoc().add_root(root)