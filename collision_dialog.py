# Interpreter: CPython 3.8 (64-bit)
# Name: Collision Detection Dialog
# Comment: Create Gantry colliders for collision detection and evaluation.
# Module: Structure definition, Plan setup

import sys

from System.Windows import Visibility
from System.Windows.Controls import (TreeViewItem, StackPanel,
                                     ListBoxItem, Label, ToolTip)
from System.Windows.Shapes import Ellipse
from System.Windows.Media import BrushConverter
from System.Windows import Thickness
from System.Windows.Forms import Application

from .external import get_current, RayWindow, CompositeAction
from .case_comment_data import set_validation_comment

from .collision_rois import (beamset_rois, Overlaps, __FAB__,
                             nominal_beam_name, nominal_iso_name)

import logging

_logger = logging.getLogger('CollisionDialog')

__COMMENT_HEADING__ = "Collision"

XAML = """
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        xmlns:d="http://schemas.microsoft.com/expression/blend/2008"
        xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
        xmlns:System="clr-namespace:System;assembly=mscorlib"
        Title="Collision Detection"
        SizeToContent="WidthAndHeight"
        Foreground="#FF832F2F"
        Topmost="True"
        WindowStartupLocation="CenterOwner"
        ResizeMode="NoResize"
        WindowStyle="ThreeDBorderWindow" MinWidth="192"
        FontSize="24">

    <Window.Resources>
        <BooleanToVisibilityConverter x:Key="BooleanToVisibilityConverter"/>
        <RadialGradientBrush x:Key="LED_Mask" GradientOrigin="0.4,0.3">
            <GradientStop Color="#96000000" Offset="0.463"/>
            <GradientStop Color="#C8000000" Offset="0.267"/>
            <GradientStop Color="#FF000000" Offset="0.071"/>
        </RadialGradientBrush>
        <RadialGradientBrush x:Key="LED_Stroke">
            <GradientStop Color="LightGray" Offset="0.8"/>
            <GradientStop Color="DarkGray" Offset="0.9"/>
            <GradientStop Color="#FF969696" Offset="0.95"/>
        </RadialGradientBrush>
        <Style TargetType="{x:Type StackPanel}">
            <Setter Property="Margin" Value="5"/>
        </Style>
        <Style TargetType="{x:Type Ellipse}">
            <Setter Property="OpacityMask" Value="{DynamicResource LED_Mask}"/>
            <Setter Property="Stroke" Value="{DynamicResource LED_Stroke}"/>
            <Setter Property="Effect" Value="{DynamicResource LED_Shadow}"/>
            <Setter Property="Width" Value="25"/>
            <Setter Property="Height" Value="25"/>
            <Setter Property="StrokeThickness" Value="3"/>
            <Setter Property="Margin" Value="5"/>
        </Style>
        <Style TargetType="{x:Type TreeViewItem}">
            <Setter Property="IsExpanded" Value="True"/>
        </Style>
        <Style TargetType="{x:Type CheckBox}">
            <Setter Property="VerticalContentAlignment" Value="Center"/>
        </Style>
        <Style TargetType="{x:Type Button}">
            <Setter Property="Margin" Value="5,0"/>
            <Setter Property="Padding" Value="5"/>
        </Style>
        <DropShadowEffect x:Key="LED_Shadow" Opacity="0.4" ShadowDepth="3"
            BlurRadius="6"/>
        <CheckBox x:Key="DisplayLoading" IsChecked="True"/>
    </Window.Resources>
    <Window.TaskbarItemInfo>
        <TaskbarItemInfo ProgressState="Normal" ProgressValue="50"/>
    </Window.TaskbarItemInfo>

    <StackPanel Background="#FFE6E6E6" MinHeight="20" Margin="0">
        <StackPanel x:Name="Loading_Progress_Panel" Visibility="{Binding
                Converter={StaticResource BooleanToVisibilityConverter},
                Mode=OneWay, Path=IsChecked}"
                DataContext="{DynamicResource DisplayLoading}">
            <ProgressBar x:Name="Loading_Progress_Bar" IsIndeterminate="True"
                Height="20" Margin="10"/>
            <Label x:Name="Loading_Progress_Text"
                Content="Loading Beam OARs..." HorizontalAlignment="Center"/>
        </StackPanel>
        <StackPanel>
            <StackPanel.Style>
                <Style TargetType="{x:Type StackPanel}">
                    <Setter Property="Visibility" Value="Collapsed" />
                    <Style.Triggers>
                        <DataTrigger Binding="{Binding Visibility,
                                ElementName=Loading_Progress_Panel}"
                                Value="Collapsed">
                            <Setter Property="Visibility" Value="Visible" />
                        </DataTrigger>
                        <DataTrigger Binding="{Binding Visibility,
                                ElementName=Loading_Progress_Panel}"
                                Value="Visible">
                            <Setter Property="Visibility" Value="Collapsed" />
                        </DataTrigger>
                    </Style.Triggers>
                </Style>
            </StackPanel.Style>
            <DockPanel>
                <Expander x:Name="expander" ExpandDirection="Left"
                        IsExpanded="False">

                    <Expander.Header>
                        <DockPanel VerticalAlignment="Stretch"
                                MinHeight="{Binding ActualHeight,
                                ElementName=ROI_Selection_Stack,
                                Mode=OneWay}" >
                            <TextBlock HorizontalAlignment="Center"
                                    VerticalAlignment="Center">
                                <TextBlock.LayoutTransform>
                                    <RotateTransform Angle="-90"/>
                                </TextBlock.LayoutTransform>
                                <Run Text="Options"/>
                            </TextBlock>
                        </DockPanel>
                    </Expander.Header>
                    <StackPanel x:Name="ROI_Selection_Stack"
                            VerticalAlignment="Top" Visibility="{Binding
                            IsExpanded, Converter={StaticResource
                            BooleanToVisibilityConverter},
                            ElementName=expander}">
                        <Expander Header="ROIs filters" IsExpanded="False">
                            <StackPanel>
                                <CheckBox x:Name="includeExternal"
                                    Content="_External" IsChecked="True" />
                                <CheckBox x:Name="includeSupport"
                                    Content="_Support (e.g. Couch)"
                                    IsChecked="True"/>
                                <CheckBox x:Name="includeOthers"
                                    Content="All Others"/>
                            </StackPanel>
                        </Expander>
                        <Label Content="Select ROIs for evaluation"/>
                        <ListBox x:Name="Eval_ROIs" MinHeight="100"
                                SelectionMode="Multiple">
                            <ListBoxItem Content="Test"/>
                        </ListBox>
                        <StackPanel Orientation="Horizontal">
                            <CheckBox x:Name="expMargin" IsChecked="False"
                                Content="Use Margin?" />
                            <TextBox x:Name="expMargin_Value" Text="0"
                                Margin="10,0,0,0"
                                VerticalContentAlignment="Center"
                                VerticalAlignment="Center"
                                Visibility="{Binding IsChecked,
                                Converter={StaticResource
                                    BooleanToVisibilityConverter},
                                ElementName=expMargin}"/>
                            <Label Content="cm" Visibility="{Binding
                                IsChecked, Converter={StaticResource
                                BooleanToVisibilityConverter},
                                ElementName=expMargin}"/>
                        </StackPanel>
                        <CheckBox x:Name="UpdateComment" IsChecked="True"
                                Content="Update plan commment?" Margin="5,0">
                            <CheckBox.ToolTip>
                                Update the plan comment with the status of
                                the check.\nNOTE: Validation will not be
                                updated if a collision has been detected.
                            </CheckBox.ToolTip>
                        </CheckBox>
                    </StackPanel>
                </Expander>
                <Separator Style="{StaticResource
                    {x:Static ToolBar.SeparatorStyleKey}}" />
                <DockPanel>
                    <StackPanel Orientation="Horizontal"
                            DockPanel.Dock="Bottom"
                            HorizontalAlignment="Center">
                        <Button x:Name="Delete" Content="Delete"
                            IsCancel="True"/>
                        <Button x:Name="Keep" Content="Keep"
                            IsDefault="True"/>
                    </StackPanel>
                    <StackPanel Orientation="Horizontal">
                        <TreeView x:Name="BeamTreeView" >
                            <TreeViewItem Header="Iso1">
                                <StackPanel Orientation="Horizontal">
                                    <StackPanel.ToolTip>
                                        TestTooltip
                                    </StackPanel.ToolTip>
                                    <Ellipse Fill="Yellow"/>
                                    <Label Content="Test"/>
                                </StackPanel>
                            </TreeViewItem>
                        </TreeView>
                        <StackPanel x:Name="Main_Status_StackPanel">
                            <Button x:Name="CheckPerBeam"
                                Content="Recheck Beams"/>
                            <StackPanel x:Name="Collision_LED_Container">
                                <Ellipse Fill="Black" Width="80"
                                    Height="{Binding ActualWidth, Mode=OneWay,
                                        RelativeSource={RelativeSource Self}}"
                                    Margin="10"/>
                            </StackPanel>
                        </StackPanel>
                    </StackPanel>
                </DockPanel>
            </DockPanel>
            <StatusBar Height="22">
                <StatusBarItem Visibility="{Binding Visibility,
                        ElementName=beam_in_progress}">
                    <ProgressBar x:Name="ProgressBar"  Height="14"
                        MinWidth="100" Value="50"/>
                </StatusBarItem>
                <StatusBarItem Content="Checking Beam "
                    Visibility="{Binding Visibility,
                        ElementName=beam_in_progress}"/>
                <StatusBarItem x:Name="beam_in_progress"
                    Visibility="Collapsed"/>
            </StatusBar>
        </StackPanel>
        <CheckBox x:Name="checkBox" VerticalAlignment="Center"
            HorizontalAlignment="Center" IsChecked="{Binding Path=IsChecked}"
            DataContext="{DynamicResource DisplayLoading}"/>
    </StackPanel>
</Window>
"""


class BeamIsoTreeViewItem(TreeViewItem):
    def __init__(self, name, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._name = name
        self.Header = self._name


class Status_LED(Ellipse):
    _color = ''
    _name = ''
    _status_to_color_map = {'OK': 'Lime',
                            'Collision': 'Red',
                            'Unknown': 'Yellow'}

    def __init__(self, name, *args, **kwargs):
        self._name = name
        super().__init__(*args, **kwargs)

        self._color_map_to_status = dict(
            map(reversed, self._status_to_color_map.items()))

    @property
    def status(self):
        return self._color_map_to_status[self._color]

    @status.setter
    def status(self, status):
        _logger.debug(f"{self}: {status=}")
        color = self._status_to_color_map['Unknown']
        if status in self._status_to_color_map:
            color = self._status_to_color_map[status]
        elif status in self._color_map_to_status:
            color = status

        self.Color = color

    @property
    def Color(self):
        return self._color

    @Color.setter
    def Color(self, color):
        if color not in self._color_map_to_status:
            color = self._status_to_color_map['Unknown']

        if color != self._color:
            self._color = color
            self.Fill = BrushConverter().ConvertFrom(color)

    def __str__(self):
        return f'{self._name} LED'


class BeamIconStackPanel(StackPanel):
    _icon = None
    _label = None
    _beam_name = ''
    _colliders = None

    def __init__(self, beam_name, color=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._icon = Status_LED(beam_name)
        self._label = Label()
        self.Children.Add(self._icon)
        self.Children.Add(self._label)
        self.Orientation = 0

        self.ToolTip = ToolTip()

        self.beam_name = beam_name
        self.Color = color

    @property
    def beam_name(self):
        return self._beam_name

    @beam_name.setter
    def beam_name(self, name):
        self._beam_name = name
        self._label.Content = name

    @property
    def Color(self):
        return self._icon.Color

    @Color.setter
    def Color(self, color):
        self._icon.Color = color

    @property
    def beam_status(self):
        return self._icon.status

    @beam_status.setter
    def beam_status(self, status):
        self._icon.status = status

    @property
    def colliders(self):
        return self._colliders

    @colliders.setter
    def colliders(self, colliders):
        if not colliders:
            colliders = ''

        self._colliders = f'{colliders}'

        if self._colliders:
            content = f'Collisions with: {self._colliders}'
            logging.debug(f"{content=}")
            self.ToolTip.Content = content
            self.beam_status = 'Collision'
        else:
            self.ToolTip.Content = 'No collisions'
            self.beam_status = 'OK'


class CollisionDetectionDialogWindow(RayWindow):
    # Expected objects from XAML
    Loading_Progress_Panel = None  # StackPanel
    Loading_Progress_Bar = None  # ProgressBar
    Loading_Progress_Text = None  # Label
    ROI_Selection_Stack = None  # StackPanel
    includeExternal = None  # CheckBox
    includeSupport = None  # CheckBox
    includeOthers = None  # CheckBox
    expMargin = None  # CheckBox
    expMargin_Value = None  # TextBox
    Collision = None  # Ellipse
    Collision_LED_Container = None  # StackPanel
    beam_in_progress = None  # StatusBarItem
    checkBox = None  # CheckBox
    Eval_ROIs = None  # ListBox
    CheckPerBeam = None  # Button
    Main_Status_StackPanel = None  # StackPanel
    # Resources: self.Resources['']

    beam_set = None
    iso_beam_items = None   # dict relating isocenter objects.
    beam_items = None       # dict of only the beam_stacks
    _overlaps = None
    results = None          # Dict to store results
    beamset_rois = None
    _margin = 0

    def __init__(self, beam_set, results, full_arc_check=False):
        self.LoadComponent(XAML)

        self.full_arc_check = full_arc_check
        self.beam_set = beam_set

        self.ContentRendered += self.__rendered__
        self.CheckPerBeam.Click += self.__check_beams__
        self.Closing += self._Closing
        self.Keep.Click += self.Keep_Click

        self.includeExternal.Checked += self.update_eval_rois_list
        self.includeExternal.Unchecked += self.update_eval_rois_list
        self.includeSupport.Checked += self.update_eval_rois_list
        self.includeSupport.Unchecked += self.update_eval_rois_list
        self.includeOthers.Checked += self.update_eval_rois_list
        self.includeOthers.Unchecked += self.update_eval_rois_list

        self.expMargin_Value.TextChanged += self.margin_updated

        self.checkBox.Visibility = Visibility.Collapsed

        self.Eval_ROIs.Items.Clear()
        self.BeamTreeView.Items.Clear()

        self.Collision_LED = Status_LED('Master Collision')
        self.Collision_LED.Width = 80
        self.Collision_LED.Height = 80

        self.Collision_LED.Margin = Thickness(10.0)
        self.Collision_LED_Container.Children.Clear()
        self.Collision_LED_Container.Children.Add(self.Collision_LED)

        self.Collision

        self.results = results

        self.beam_items = []
        iso_beams = {}

        # Add Indicator for full arc/CBCT collision to main stack panel
        cbct = BeamIconStackPanel('CBCT/Full Arc')
        if not full_arc_check:
            cbct.Visibility = Visibility.Collapsed
        self.Main_Status_StackPanel.Children.Add(cbct)
        self.CBCT_Collider_LED = cbct

        for beam in self.beam_set.Beams:
            # Build the tree of isocenters, and populate the iso_beams
            # dictionary with an entry for each beam at this isocenter named
            # after the actual beam name (enforced unique in RS)
            gantry_name = nominal_beam_name(beam)
            iso_name = nominal_iso_name(beam.Isocenter)
            stack_label = f'{beam.Name} ({gantry_name})'
            beam_dict = {'name': beam.Name,
                         'stack': BeamIconStackPanel(stack_label),
                         'beam': beam,
                         'gantry': gantry_name}

            if iso_name not in iso_beams:
                iso_item = BeamIsoTreeViewItem(iso_name)
                self.BeamTreeView.Items.Add(iso_item)
                iso_beams[iso_name] = {
                    'viewitem': iso_item,
                    'beams': {beam.Name: beam_dict}}
            else:
                iso_item = iso_beams[iso_name]['viewitem']
                iso_beams[iso_name]['beams'][beam.Name] = beam_dict

            iso_item.AddChild(beam_dict['stack'])

            self.beam_items.append(beam_dict)

        self.iso_beam_items = iso_beams
        Application.DoEvents()

    def update_all_leds(self, status):
        _logger.debug(f"Updating all leds to {status}")
        self.Collision_LED.status = status
        for stack in [bdict['stack']
                      for iso in self.iso_beam_items.values()
                      for bdict in iso['beams'].values()]:
            stack.beam_status = status

    def _processing_callback(self, value, step_name=""):
        self.beam_in_progress.Visibility = Visibility.Visible
        self.beam_in_progress.Content = f"{step_name}"
        self.ProgressBar.Value = value*100
        Application.DoEvents()
        _logger.debug(f"{value=}")

    def invalidated(self, value):
        if not value:
            self.update_all_leds('Unknown')

    def margin_updated(self, sender, event):
        # Cast the value into a float
        _logger.debug(f"{sender=} {event=}")
        try:
            value = max(float(sender.Text), 0)
        except ValueError as exc:
            m = "Couldn't get int from value given text {}".format(sender.Text)
            _logger.debug(m)
            _logger.exception(exc)
            value = 0

        if sender.Text != f'{value:.1f}' and sender.Text != '':
            sender.Text = f'{value:.1f}'

        if self._margin != value:
            self._overlaps.isValid = False
            self._margin = value

    def __loading_prog_cb__(self, progress, text=''):
        self.Loading_Progress_Bar.IsIndeterminate = False
        self.Loading_Progress_Bar.Value = progress
        self.Loading_Progress_Text.Content = f'Loading Beam OARs...{text}'
        Application.DoEvents()

    def __rendered__(self, caller, event):
        # Wait for rendered to do the slow things so we can update the GUI
        self._overlaps = Overlaps(invalidation_cb_fn=self.invalidated,
                                  iter_cb_fn=self._processing_callback,
                                  gantry_cb_fn=self.__loading_prog_cb__,
                                  beam_set=self.beam_set,
                                  full_arc_check=self.full_arc_check)

        Application.DoEvents()

        self.beamset_rois = beamset_rois(self.beam_set)
        _logger.debug(f"{self.beamset_rois = }")

        self.update_eval_rois_list()
        self.Resources['DisplayLoading'].IsChecked = False
        Application.DoEvents()
        self.__check_beams__()

    def _get_roi_set_for_settings(self):
        if self.includeOthers.IsChecked:
            _logger.debug("includeOthers checked")
            return {roi for roi_set in self.beamset_rois for roi in roi_set
                    if roi not in self._overlaps.beamrois_set}

        rois_set = set()
        if self.includeExternal.IsChecked and 'External' in self.beamset_rois:
            _logger.debug("includeExternal checked")
            rois_set |= self.beamset_rois['External']

        if self.includeSupport.IsChecked and 'Support' in self.beamset_rois:
            _logger.debug("includeSupport checked")
            rois_set |= self.beamset_rois['Support']

        return rois_set

    def update_eval_rois_list(self, sender=None, event=None):
        latest_set = self._get_roi_set_for_settings()
        if self.evalrois_list != latest_set:
            if self._overlaps:
                _logger.debug("Invalidating overlaps")
                self._overlaps.isValid = False

        self.Eval_ROIs.Items.Clear()

        _logger.debug(f"{latest_set = }\n{self.evalrois_list = }")
        for roi_n in sorted(latest_set):
            lbi = ListBoxItem()
            lbi.Content = roi_n
            lbi.IsSelected = True
            self.Eval_ROIs.Items.Add(lbi)

    @property
    def selected_rois(self):
        return {f'{item.Content!s}' for item in self.Eval_ROIs.Items
                if item.IsSelected}

    @property
    def evalrois_list(self):
        return {f'{item.Content!s}' for item in self.Eval_ROIs.Items}

    @property
    def overlaps(self):
        if not self._overlaps or not self._overlaps.isValid:
            _logger.debug("Overlaps not valid, running anew")
            self._overlaps.check_rois(self.selected_rois, margin=self._margin)
        return self._overlaps

    def __check_beams__(self, sender=None, event=None):
        _logger.debug(f"{sender=} {event=}")
        self.update_all_leds('Unknown')
        overlaps = self.overlaps
        gantry2coll = overlaps.colliders_by_gantry

        _logger.debug(f"Collision status: {overlaps=}")

        if not overlaps.hasCollision:
            self.Collision_LED.status = "OK"

        for beam_dict in self.beam_items:
            gantry_name = overlaps.beam_map[beam_dict['name']]
            try:
                beam_dict['stack'].colliders = gantry2coll[gantry_name]
            except KeyError:
                logging.debug(f"Couldn't find {gantry_name} in colliders.")

        cbct = None
        if __FAB__ in overlaps.beam_map:
            cbct = gantry2coll[overlaps.beam_map[__FAB__]]
        _logger.debug(f"{cbct=}")
        self.CBCT_Collider_LED.colliders = cbct

        self.beam_in_progress.Visibility = Visibility.Collapsed

    def _Closing(self, *args, **kwargs):
        _logger.debug(f"Closing(*{args}, **{{{kwargs}}})")
        self.results['UpdateComment'] = self.UpdateComment.IsChecked
        self.results['Overlaps'] = self._overlaps
        self._overlaps.CleanUp(self.DialogResult)

    def Keep_Click(self, sender, event):
        self.DialogResult = True
        self.Close()


def check_collision_dialog(plan, beam_set, full_arc_check=False):
    # TODO: Handle full arc check

    results = {}
    dlg = CollisionDetectionDialogWindow(beam_set, results,
                                         full_arc_check=full_arc_check)

    try:
        with CompositeAction("Collision Check") as CA:
            res = dlg.ShowDialog()

            if res:
                if CA.is_root:
                    # We can undo by popping out of the CompositeAction with a
                    # warning that we catch.
                    raise Warning("Closed with cancel")
                else:
                    # Composite action was not root, so we have to delete
                    # contours manually.
                    _logger.info("Closed with cancel, Removing ROIs.")
                    results['Overlaps'].CleanUp()
            else:
                _logger.info("Retaining ROIs.")
    except Warning as e:
        _logger.warning("{}".format(e), exc_info=True)

    status = {'status': results['Overlaps'].hasCollision,
              'UpdateComment': (bool(results['UpdateComment'])
                                if 'UpdateComment' in results else True),
              'overlaps': results['Overlaps']}

    _logger.debug(f"Closed with result {res = }")

    return status


if __name__ == '__main__':
    log_fmt = ('%(asctime)s: %(name)s.%(funcName)s:%(lineno)d'
               ' - %(levelname)s: %(message)s')

    logging.basicConfig(format=log_fmt, level=logging.DEBUG, stream=sys.stdout,
                        force=True)

    beam_set = get_current("BeamSet")
    plan = get_current("Plan")

    status = check_collision_dialog(plan, beam_set)
    if status['UpdateComment']:
        passes = not status['status']
        _logger.info(f"Updating validation status for plan to {passes=}.")
        set_validation_comment(plan, beam_set, __COMMENT_HEADING__, passes)
