import numpy as np
import pandas as pd

from bokeh.models import GeoJSONDataSource, ColumnDataSource, HoverTool, \
                         LogColorMapper, FuncTickFormatter, BasicTickFormatter, \
                         GMapOptions
from bokeh.models.widgets import RadioButtonGroup, Div, CheckboxGroup, Slider
from bokeh.models.ranges import FactorRange, DataRange1d, Range1d
from bokeh.layouts import widgetbox
from bokeh.plotting import figure, gmap
from bokeh.palettes import gray
from bokeh.tile_providers import CARTODBPOSITRON, STAMEN_TERRAIN

from ihelpers import aggregate_data_for_time_series, get_colors

def _create_choropleth_map(source, width=600, height=1000):
    """ Create a choropleth map with of incidents in Amsterdam-Amstelland.
    
    params
    ------
    source: a Bokeh GeoJSONDataSource object containing the data

    return
    ------
    a Bokeh figure showing the spatial distribution of incidents
    in over the region
    """

    map_colors = ['#f2f2f2', '#fee5d9', '#fcbba1', '#fc9272', '#fb6a4a', '#de2d26']
    color_mapper = LogColorMapper(palette=map_colors)
    nonselection_color_mapper = LogColorMapper(palette=gray(6)[::-1])
    tooltip_info = [("index", "$index"),
                    ("(x,y)", "($x, $y)"),
                    ("#incidents", "@incident_rate"),
                    ("location id", "@location_id")]
    map_tools = "pan,wheel_zoom,tap,hover,reset"

    # get google maps API key
    with open("./Data/googlemapskey.txt") as f:
        maps_api_key = f.readline()

    map_options = GMapOptions(lat=52.35, lng=4.9, map_type="roadmap", zoom=11)
    p = gmap(maps_api_key, map_options, title="Amsterdam-Amstelland",
             tools=map_tools, plot_width=width, plot_height=height,
             x_axis_location=None, y_axis_location=None)

    # p = figure(title="Spatial distribution of incidents in Amsterdam-Amstelland",
    #            tools=map_tools, x_axis_location=None, y_axis_location=None,
    #            height=height, width=width, tooltips=tooltip_info)

    # p.x_range = Range1d(4.66, 5.10)
    # p.y_range = Range1d(52.18, 52.455)
    # p.grid.grid_line_color = None
    # p.add_tile(CARTODBPOSITRON)

    patches = p.patches('xs', 'ys', source=source,
                        fill_color={'field': 'incident_rate', 'transform': color_mapper},
                        fill_alpha=0.5, line_color="black", line_width=0.3,
                        nonselection_fill_color={'field': 'incident_rate',
                                                 'transform': nonselection_color_mapper})


    return p, patches

def _create_time_series(dfincident, agg_by, pattern, group_by,
                        types, width=500, height=350):
    """ Create a time series plot of the incident rate. 

    params
    ------
    agg_field: the column name to aggregate by.
    pattern_field: the column name that represents the pattern length to
                 be investigated / plotted.
    incident_types: array, the incident types to be included in the plot.

    return
    ------
    tuple of (Bokeh figure, glyph) showing the incident rate over time.
    """

    def xticker():
        """ Custom function for positioning ticks """
        if (int(tick)%10 == 0) | (len(tick)>2):
            return tick
        else:
            return ""

    x, y, labels = aggregate_data_for_time_series(dfincident, agg_by, 
                                                  pattern, group_by,
                                                  types, None)

    if group_by != "None":
        colors, ngroups = get_colors(len(labels))
        source = ColumnDataSource({"xs": x[0:ngroups],
                                   "ys": y[0:ngroups],
                                   "cs": colors,
                                   "label": labels[0:ngroups]})
    else:
        source = ColumnDataSource({"xs": [x],
                                   "ys": [y],
                                   "cs": ["green"],
                                   "label": ["avg incidents count"]})

    # create plot
    timeseries_tools = "pan,wheel_zoom,reset,xbox_select,hover,save"
    p = figure(title="Time series of incident rate",
               tools=timeseries_tools, width=width, height=height,
               x_range=FactorRange(*x))

    glyph = p.multi_line(xs="xs", ys="ys", legend="label", line_color="cs", 
                 source=source, line_width=3)

    # format legend
    p.legend.label_text_font_size = "7pt"
    p.legend.background_fill_alpha = 0.5
    p.legend.location = 'top_left'
    # format ticks
    p.xaxis.formatter = FuncTickFormatter.from_py_func(xticker)
    p.xaxis.major_tick_line_width = 0.1
    p.xaxis.major_label_text_font_size = "5pt"
    p.xaxis.group_text_font_size = "6pt"
    p.xaxis.major_tick_line_color = None
    p.x_range.group_padding = 0.0
    p.x_range.range_padding = 0.0
    p.x_range.subgroup_padding = 0.0

    #p.yaxis.major_tick_line_color = "Red"
    #p.yaxis.major_label_text_font_size = "6pt"
    #p.y_range = Range1d(np.min(y)*0.9, np.max(y)*1.1)
    return p, glyph

def _create_radio_button_group(options):
    radio_button_group = RadioButtonGroup(
        labels=[option for option in options], active=0)
    return radio_button_group

def _create_type_filter(incident_types):
    checkbox_group = CheckboxGroup(
        labels=[t for t in incident_types],
        active=list(np.arange(0,len(incident_types))))
    header = Div(text="Incident types:", width=200, height=100)
    return checkbox_group #widgetbox(children=[header, checkbox_group])

def _get_slider_params(time_unit):
    """ Get the parameters for the time slider.

    params
    ------
    time_unit: str, one of {'hour', 'day', 'week', 'month'}. Indicates
        the time unit that the slider must slide over.

    return
    ------
    tuple of parameters to give to the slider :
    (start, end, value, step, title)
    """
    if time_unit=="hour":
        return 0, 23, 0, 1, "Hour of day"
    elif time_unit=="day":
        return 1, 7, 1, 1, "Day of week"
    elif time_unit=="week":
        return 1, 52, 1, 1, "Week number"
    elif time_unit=="month":
        return 1, 12, 1, 1, "Month number"
    else:
        ValueError("Unsupported value for time_unit, must be one of:\
                    {'hour', 'day', 'week', 'month'}.")

def create_slider(time_unit="hour"):
    start, end, value, step, title = _get_slider_params(time_unit)
    return Slider(start=start, end=end, value=value, step=step, title=title)

""" Replaced by _create_radio_button_group for now
def _create_pattern_selection_widget():
    options = ["Daily", "Weekly", "Yearly"]
    buttons = _create_radio_button_group(options)
    header = Div(text="Pattern:", width=100)
    return buttons#widgetbox(children=[header, buttons])

def _create_aggregation_widget(options):
    buttons = _create_radio_button_group(options)
    header = Div(text="Aggregate by", width=100)
    return buttons #widgetbox(children=[header, buttons])


def _create_groupby_widget():
    options = ["None", "Type", "Day of Week", "Year"]
    buttons = _create_radio_button_group(options)
    header = Div(text="Group by", width=100)
    return buttons #widgetbox(children=[header, buttons])
"""