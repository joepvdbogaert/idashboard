import numpy as np
import pandas as pd

from bokeh.models import GeoJSONDataSource, ColumnDataSource, HoverTool, LogColorMapper, FuncTickFormatter
from bokeh.models.widgets import RadioButtonGroup, Div, CheckboxGroup
from bokeh.models.ranges import FactorRange
from bokeh.layouts import widgetbox
from bokeh.plotting import figure
from bokeh.palettes import gray
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


    p = figure(title="Spatial distribution of incidents in Amsterdam-Amstelland",
               tools=map_tools, x_axis_location=None, y_axis_location=None,
               height=height, width=width, tooltips=tooltip_info)

    p.grid.grid_line_color = None
    patches = p.patches('xs', 'ys', source=source,
                        fill_color={'field': 'incident_rate', 'transform': color_mapper},
                        fill_alpha=0.7, line_color="black", line_width=0.3,
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

    def ticker():
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
    p.xaxis.formatter = FuncTickFormatter.from_py_func(ticker)
    p.xaxis.major_tick_line_width = 0.1
    p.xaxis.major_label_text_font_size = "5pt"
    p.xaxis.group_text_font_size = "6pt"
    p.xaxis.major_tick_line_color = None

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