import logging
from System.Windows.Media import Brushes
from System.Windows.Controls import (Border, TextBlock, RowDefinition,
                                     ColumnDefinition, ComboBoxItem, Separator)
from System.Windows.Documents import Bold, Run, LineBreak

from .external import (get_current, obj_name, MockObject,
                       MockPrescriptionDoseReference, RayWindow)
from .plans import beamset_conformity_indices

from math import inf

_logger = logging.getLogger(__name__)

INDICES_DICT = {
    'Brain': {
        'Small': {
            'Vol': (0, 2),
            'GI': {'ok': 4.57, 'min': 2.71, 'max': 8.03},
            'PCI': {'ok': 0.56, 'min': 0.40, 'max': 0.82}
        },
        'Medium': {
            'Vol': (2, 10),
            'GI': {'ok': 4.28, 'min': 2.40, 'max': 7.29},
            'PCI': {'ok': 0.74, 'min': 0.65, 'max': 0.88}
        },
        'Large': {
            'Vol': (10, inf),
            'GI': {'ok': 3.66, 'min': 2.43, 'max': 5.36},
            'PCI': {'ok': 0.75, 'min': 0.71, 'max': 0.93}
        }
    },
    'Lung': {
        'Very Small': {
            'Vol': (0, 5),
            'HI': {'ok': 0.30, 'min': 0.15, 'max': 0.42},
            'GI': {'ok': 5.17, 'min': 3.92, 'max': 5.92},
            'RTOGCI': {'ok': 1.24, 'min': 1.07, 'max': 1.55},
            'PCI': {'ok': 0.74, 'min': 0.61, 'max': 0.84}
        },
        'Small': {
            'Vol': (5, 10),
            'HI': {'ok': 0.34, 'min': 0.25, 'max': 0.46},
            'GI': {'ok': 4.58, 'min': 3.62, 'max': 5.47},
            'RTOGCI': {'ok': 1.10, 'min': 1.00, 'max': 1.22},
            'PCI': {'ok': 0.83, 'min': 0.76, 'max': 0.90}
        },
        'Medium': {
            'Vol': (10, 30),
            'HI': {'ok': 0.31, 'min': 0.16, 'max': 0.43},
            'GI': {'ok': 4.57, 'min': 3.47, 'max': 5.97},
            'RTOGCI': {'ok': 1.06, 'min': 1.01, 'max': 1.10},
            'PCI': {'ok': 0.86, 'min': 0.83, 'max': 0.90}
        },
        'Large': {
            'Vol': (30, inf),
            'HI': {'ok': 0.29, 'min': 0.26, 'max': 0.33},
            'GI': {'ok': 3.75, 'min': 0.31, 'max': 4.28},
            'RTOGCI': {'ok': 1.04, 'min': 1.01, 'max': 1.06},
            'PCI': {'ok': 0.87, 'min': 0.86, 'max': 0.90}
        }
    }
}

INDEX_DIR_SMALLER_BETTER = {'RTOGCI': True,
                            'PCI': False,
                            'GI': True,
                            'HI': True}

BODYSITE_MAPPING = {'Brain': 'Brain',
                    'Head & Neck': 'Brain',
                    'Thorax': 'Lung'}


class BorderedTextBoxBlack(Border):
    def __init__(self, *args, **kwargs):
        super().__init__()

        textblock = TextBlock()
        self.Child = textblock
        self.Child.Foreground = Brushes.Black

        self.build_text(*args, **kwargs)

    def build_text(self, *args, **kwargs):
        textline = '&#10;'.join([f'{a}' for a in args])
        textline += '&#10;'.join([f'{k}: {kwargs[k]}' for k in kwargs])

        self.Child.Text = textline


class GoalBorderedText(BorderedTextBoxBlack):
    def build_text(self, goal):
        textblock = self.Child

        textline = Bold(Run(f"{goal['ok']:0.2f} "))
        textblock.Inlines.Add(textline)

        textline = Run(f"({goal['min']:0.2f} - {goal['max']:0.2f})")
        textblock.Inlines.Add(textline)


class IndexHeader(BorderedTextBoxBlack):
    def build_text(self, index_name):
        textblock = self.Child

        textline = Run(f'{index_name}')
        textblock.Inlines.Add(textline)
        textblock.Inlines.Add(LineBreak())

        if INDEX_DIR_SMALLER_BETTER[index_name]:
            textline = Run('(smaller is better)')
        else:
            textline = Run('(larger is better)')

        textline.FontSize = 12
        textblock.Inlines.Add(textline)


class SizeBorderedHeader(BorderedTextBoxBlack):
    def build_text(self, size, vol_range):
        textblock = self.Child

        textline = Run(f'{size}')
        textblock.Inlines.Add(textline)
        textblock.Inlines.Add(LineBreak())

        if vol_range[0] == 0:
            header_content = f'(V<{vol_range[1]})'
        elif vol_range[1] == inf:
            header_content = f'(V>{vol_range[0]})'
        else:
            header_content = f'({vol_range[0]}\u2264V<{vol_range[1]})'

        textline = Run(header_content)
        textline.FontSize = 12

        textblock.Inlines.Add(textline)


class IndexData(dict):
    # Class to hold dose index data for a particular site

    # volumes: type[set]  # Wait for Py 3.10 for typing
    # index_names: type[set]  # Wait for Py 3.10 for typing

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.volumes = {k: self[k]['Vol'] for
                        k in sorted(self, key=lambda a: self[a]['Vol'][0])}

        self.index_names = {index for indices in self.values()
                            for index in indices if index != 'Vol'}


class Indices(dict):
    # Class to hold indices by site.

    def __init__(self):
        super().__init__({k: IndexData(v) for k, v in INDICES_DICT.items()})


DoseIndices = Indices()


class ContentWrapper:
    data = None
    content = None

    def __init__(self, content):
        self.content = content
        # self.data = data
        _logger.debug(f"Built {self=}")

    def __str__(self):
        _logger.debug(f"Getting str for content wrapper {self=}")
        return f'{self.content}'

    ToString = __str__


class PlanComboBoxItem(ComboBoxItem):
    def __init__(self, plandata):
        super().__init__()

        planname = f"{obj_name(plandata['Plan'])}"
        bsname = f"{obj_name(plandata['BeamSet'])}"

        content = f"{planname} -- {bsname}"

        _logger.debug(f"Built {self=}")

        self.Content = ContentWrapper(content)


class TargetRoiComboBoxItem(ComboBoxItem):
    def __init__(self, roirxdata):
        super().__init__()
        name = f"{obj_name(roirxdata.OnStructure)}"
        dose = f"{roirxdata.DoseValue:.0f}"

        content = f"{name} ({dose} cGy)"
        _logger.debug(f"Built {self=}")
        self.Content = ContentWrapper(content)


class ConformityIndicesWindow(RayWindow):
    active_site = "Brain"
    roi_data = None
    # PlanSelectComboBox: type[ComboBox]  # Wait for Py 3.10 for typing
    # ROIComboBox: type[ComboBox]  # Wait for Py 3.10 for typing

    _XAML = """
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Dose Indices"
        SizeToContent="WidthAndHeight"
        Foreground="#FF832F2F"
        Topmost="True"
        WindowStartupLocation="CenterOwner"
        ResizeMode="NoResize"
        WindowStyle="ThreeDBorderWindow" MinWidth="192"
        FontSize="24">

    <Window.Resources>
        <Style TargetType="{x:Type StackPanel}">
            <Setter Property="Margin" Value="0"/>
            <Style.Triggers>
                <DataTrigger Binding="{Binding Visibility,
                    ElementName=PlanSelectPanel}" Value="Collapsed">
                    <Setter Property="Visibility" Value="Visible"/>
                </DataTrigger>
            </Style.Triggers>
        </Style>
        <Style TargetType="{x:Type Label}">
            <Setter Property="VerticalAlignment" Value="Center"/>
        </Style>
        <Style TargetType="{x:Type ColumnDefinition}">
            <Setter Property="Width" Value="Auto"/>
        </Style>
        <Style TargetType="{x:Type RowDefinition}">
            <Setter Property="Height" Value="Auto"/>
        </Style>

        <Style x:Key="ExpanderButton" TargetType="{x:Type ToggleButton}">
            <Setter Property="Height" Value="20"/>
            <Style.Triggers>
                <Trigger Property="IsChecked" Value="True">
                    <Setter Property="Content" Value="⮝"/>
                    <Setter Property="Padding" Value="1,-10,1,-10"/>
                </Trigger>
                <Trigger Property="IsChecked" Value="False">
                    <Setter Property="Content" Value="⮟"/>
                    <Setter Property="Padding" Value="1,-10,1,0"/>
                </Trigger>
            </Style.Triggers>
        </Style>
        <Style x:Key="ExpanderPanel" TargetType="{x:Type Expander}">
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="{x:Type Expander}">
                        <DockPanel>
                            <ContentPresenter x:Name="ExpandSite"
                                              DockPanel.Dock="Top"
                                              Focusable="false"
                                              Visibility="Collapsed"/>
                            <ToggleButton x:Name="HeaderSite"
                                DockPanel.Dock="Bottom"
                                IsChecked="{Binding IsExpanded,
                                    Mode=TwoWay,
                                    RelativeSource={RelativeSource
                                        TemplatedParent}}"
                                Style="{StaticResource ExpanderButton}"/>
                        </DockPanel>
                        <ControlTemplate.Triggers>
                            <Trigger Property="IsExpanded" Value="true">
                                <Setter Property="Visibility"
                                 TargetName="ExpandSite" Value="Visible"/>
                            </Trigger>
                            <Trigger Property="IsEnabled" Value="false">
                                <Setter Property="Foreground"
        Value="{DynamicResource {x:Static SystemColors.GrayTextBrushKey}}"/>
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>

    </Window.Resources>

    <StackPanel Background="#FFE6E6E6" MinHeight="20" Margin="0">
        <Expander Style="{StaticResource ExpanderPanel}">
            <DockPanel>
                <Label Content="Plan to evaluate: "/>
                <ComboBox x:Name="PlanSelectComboBox"
                          SelectionChanged="PlanChanged">
                    <ComboBoxItem/>
                    <Separator/>
                    <ComboBoxItem/>
                </ComboBox>
            </DockPanel>
        </Expander>

        <DockPanel LastChildFill="False">
            <ComboBox x:Name="ROIComboBox" DockPanel.Dock="Left"
                      SelectionChanged="ROIChanged">
                <ComboBoxItem Content="PTV50" IsSelected="True"/>
            </ComboBox>
            <Label >
                <TextBlock>
                    <Run>Volume</Run>
                    <Run x:Name="ROIVolume">50</Run>
                    <Run>cc</Run>
                </TextBlock>
            </Label>
            <StackPanel Orientation="Horizontal" DockPanel.Dock="Right">
                <Label Content="Site:"/>
                <ComboBox x:Name="Site" SelectionChanged="SiteChanged">
                    <ComboBoxItem Content="Unknown" IsSelected="True"/>
                </ComboBox>
            </StackPanel>
        </DockPanel>
        <Border BorderThickness="0,0,1,1" BorderBrush="Black" Margin="2">
            <Grid x:Name="DosesGrid">
                <Grid.RowDefinitions>
                    <RowDefinition/>
                    <RowDefinition/>
                </Grid.RowDefinitions>
                <Grid.ColumnDefinitions>
                    <ColumnDefinition/>
                    <ColumnDefinition/>
                    <ColumnDefinition/>
                    <ColumnDefinition/>
                    <ColumnDefinition/>
                    <ColumnDefinition/>
                </Grid.ColumnDefinitions>
                <Grid.Resources>
                    <Style TargetType="{x:Type Label}" >
                        <Style.Triggers>
                            <Trigger Property="Grid.Column" Value="0">
                                <Setter Property="BorderThickness"
                                        Value="2,1,1,1"/>
                            </Trigger>
                        </Style.Triggers>

                        <Setter Property="BorderThickness" Value="2"/>
                        <Setter Property="BorderBrush" Value="Black"/>
                        <Setter Property="HorizontalContentAlignment"
                                Value="Center"/>
                    </Style>
                    <Style TargetType="{x:Type TextBlock}" >
                        <Setter Property="TextAlignment" Value="Center"/>
                        <Setter Property="VerticalAlignment" Value="Center"/>
                        <Setter Property="Margin" Value="4,2"/>
                        <Setter Property="Foreground" Value="Black"/>
                    </Style>
                    <Style TargetType="{x:Type Border}">
                        <Setter Property="BorderThickness" Value="1,2,1,1"/>
                        <Setter Property="BorderBrush" Value="Black"/>
                    </Style>
                </Grid.Resources>
                <Label Grid.ColumnSpan="2" Grid.Column="0" Grid.Row="0"
                       BorderThickness="0,0,1,1"/>

                <Border Grid.Column="2" Grid.Row="0">
                    <TextBlock Text="Very Small&#10;(V&lt;5cc)"/>
                </Border>

                <Label Grid.Column="3" Grid.Row="0"
                       Content="Small&#10;(5cc&lt;V&lt;10cc)" />
                <Label Grid.Column="4" Grid.Row="0"
                       Content="Medium&#10;(10cc&lt;V&lt;30cc)" />
                <Label Grid.Column="5" Grid.Row="0"
                       Content="Large&#10;(V&gt;30cc)" />
                <Label Grid.Column="0" Grid.Row="1" Content="CI"/>
                <Label Grid.Column="1" Grid.Row="1" Content="Value"/>
                <Border Grid.Column="3" Grid.Row="1">
                    <TextBlock>
                        <Run FontWeight="Bold" Text="1.24 " />
                        <Run Text="(1.07 - 1.55)"/>
                    </TextBlock>
                </Border>
                <Label Content="1" Grid.Column="2" Grid.Row="1"/>

                <Rectangle x:Name="ActiveVolume" Grid.RowSpan="2147483647"
                        Grid.ColumnSpan="1" Grid.Column="2" Panel.ZIndex="-1">
                    <Rectangle.Fill>
                        <SolidColorBrush
    Color="{DynamicResource {x:Static SystemColors.ActiveCaptionColorKey}}"/>
                    </Rectangle.Fill>
                </Rectangle>

                <TextBlock x:Name="ErrorBlock"
                           Grid.Column="2" Grid.ColumnSpan="4" Grid.Row="1"
                           FontSize="30" FontWeight="Bold" Foreground="Red">
                    <Run>Dose not calculated, or an error has occured.</Run>
                    <LineBreak/>
                    <Run>Check execution log.</Run>
                </TextBlock>

            </Grid>
        </Border>
        <Button Name="btnCancel" IsCancel="true"
                Padding="0" Width="0" Height="0"/>
    </StackPanel>
</Window>
    """

    def __init__(self, beamset=None, plan=None, casedata=None):

        self.LoadComponent(self._XAML)

        casedata = get_current("Case") if casedata is None else casedata
        plan = get_current("Plan") if plan is None else plan
        beamset = get_current("BeamSet") if beamset is None else beamset

        self.roi_data = {'ROIvol': 0}

        # self.ROIComboBox.SelectionChanged += self.ROIChanged
        self.build_plan_list(beamset, plan, casedata)

        # Build the list of sites and add the OnChanged Event Callback
        sites = DoseIndices.keys()
        self.active_site = BODYSITE_MAPPING.get(casedata.BodySite,
                                                self.active_site)
        self.build_site_dropdown(sites)

        self.build_labels()

    def build_roi_list(self, beamset, include_all_targets=True,
                       include_all_rois=False):

        _logger.debug("Building roi list")

        self.ROIComboBox.Items.Clear()

        ptmodel = beamset.PatientSetup.CollisionProperties.ForPatientModel
        rois = set(ptmodel.RegionsOfInterest)

        target_rois = {roi for roi in rois
                       if roi.OrganData.OrganType == 'Target'}

        _logger.debug(f"{target_rois=}")

        ppdr = beamset.Prescription.PrimaryPrescriptionDoseReference
        primary_rxdose = ppdr.DoseValue
        pdrlist = []

        if ppdr.PrescriptionType == 'DoseAtVolume':
            pdrlist = [ppdr]

        _logger.debug(f"Initial {pdrlist=}")
        _logger.debug(f"{primary_rxdose=}")

        if len(beamset.Prescription.PrescriptionDoseReferences) > 1:
            pdrlist.append(None)
            pdrlist += [pdr for pdr in
                        beamset.Prescription.PrescriptionDoseReferences
                        if pdr.PrescriptionType == 'DoseAtVolume'
                        and pdr.OnStructure is not None]

        targets_without_rx = target_rois - {pdr.OnStructure for pdr
                                            in pdrlist if pdr is not None}
        if targets_without_rx and include_all_targets:
            pdrlist.append(None)
            for roi in targets_without_rx:
                pdrlist.append(MockPrescriptionDoseReference(roi,
                                                             primary_rxdose))

        other_rois = rois - {pdr.OnStructure for pdr
                             in pdrlist if pdr is not None}
        if other_rois and include_all_rois:
            pdrlist.append(None)
            for roi in other_rois:
                pdrlist.append(MockPrescriptionDoseReference(roi,
                                                             primary_rxdose))

        if pdrlist[0] is None:
            pdrlist.pop(0)

        _logger.debug(f"{pdrlist=}")

        self.pdrlist = pdrlist

        for pdr in pdrlist:
            if pdr is None:
                self.ROIComboBox.Items.Add(Separator())
            else:
                name = f"{obj_name(pdr.OnStructure)}"
                dose = f"{pdr.DoseValue:.0f}"
                roicbitem = ComboBoxItem()
                roicbitem.Content = f"{name} ({dose} cGy)"

                self.ROIComboBox.Items.Add(roicbitem)

        self.ROIComboBox.Items[0].IsSelected = True

    def build_plan_list(self, beamset, selected_plan=None, casedata=None):
        # Build the list of plans to select from.

        if selected_plan:
            plans = []

            if casedata is None:
                casedata = MockObject()
                casedata.TreatmentPlans = [selected_plan]

            for plan in casedata.TreatmentPlans:
                plans += [{'BeamSet': bs,
                           'Plan': plan,
                           'Selected': bs.UniqueId == beamset.UniqueId}
                          for bs in plan.BeamSets]
                plans.append(None)

            # Remove the extra "None"
            plans.pop()
        else:
            plans = [{'BeamSet': beamset,
                      'Plan': 'Current Plan',
                      'Selected': True}]

        if casedata and selected_plan in casedata.TreatmentPlans:
            plans = [{'BeamSet': bs,
                      'Plan': plan,
                      'Selected': bs.UniqueId == beamset.UniqueId}
                     for plan in casedata.TreatmentPlans
                     for bs in plan.BeamSets]
        elif selected_plan:
            plans = [{'BeamSet': beamset,
                      'Plan': selected_plan,
                      'Selected': bs.UniqueId == beamset.UniqueId}
                     for bs in selected_plan.BeamSets]

        _logger.debug(f'{plans=}')

        self.plans = plans

        self.PlanSelectComboBox.Items.Clear()

        for plandata in plans:
            if plandata is None:
                self.PlanSelectComboBox.Items.Add(Separator())
                continue
            planitem = ComboBoxItem()
            planname = f"{obj_name(plandata['Plan'])}"
            bsname = f"{obj_name(plandata['BeamSet'])}"

            planitem.Content = f"{planname} -- {bsname}"
            _logger.debug(f'Added {planitem=} to combobox. ')
            self.PlanSelectComboBox.Items.Add(planitem)
            if plandata['Selected']:
                planitem.IsSelected = plandata['Selected']
                self.active_plandata = plandata

        _logger.debug("Added plans to combobox")

        # Finally, rebuild the ROI list
        self.build_roi_list(beamset)

    def SiteChanged(self, sender, event):
        if sender.SelectedItem is None:
            return

        _logger.debug(f'Site change {sender.SelectedItem=}'
                      f' {self.active_site=}')
        if sender.SelectedItem.Content != self.active_site:
            self.active_site = sender.SelectedItem.Content
            self.build_labels()

    def PlanChanged(self, sender, event):
        if sender.SelectedItem is None:
            return

        _logger.debug(f'{sender=} {sender.SelectedItem=} {event=}')
        if sender.SelectedItem.Content != sender.Text:
            plandataidx = sender.Items.IndexOf(sender.SelectedItem)
            self.active_plandata = self.plans[plandataidx]
            self.build_roi_list(self.active_plandata['BeamSet'])

    def ROIChanged(self, sender, event):
        if sender.SelectedItem is None:
            return

        _logger.debug(f"{self.PlanSelectComboBox.SelectedItem=}")

        _logger.debug(f'ROI change {sender.SelectedItem=}'
                      f' {self.roi_data=}')
        if sender.SelectedItem.Content != sender.Text:
            _logger.debug(f'Roi changed from {sender.Text}'
                          f' to {sender.SelectedItem.Content}')
            beamset = self.active_plandata['BeamSet']
            rxdataidx = sender.Items.IndexOf(sender.SelectedItem)
            rxdata = self.pdrlist[rxdataidx]
            self.roi_data = beamset_conformity_indices(beamset,
                                                       rxdata.OnStructure,
                                                       rxdata.DoseValue)

            self.build_labels()

    def build_site_dropdown(self, sites):
        self.Site.Items.Clear()
        for site in sites:
            site_item = ComboBoxItem()
            site_item.IsSelected = site == self.active_site
            site_item.Content = f'{site}'

            self.Site.Items.Add(site_item)

    def build_labels(self):
        _logger.debug("Rebuilding labels")

        self.DosesGrid.Children.Clear()

        self.DosesGrid.RowDefinitions.Clear()
        self.DosesGrid.RowDefinitions.Add(RowDefinition())

        self.DosesGrid.ColumnDefinitions.Clear()
        self.DosesGrid.ColumnDefinitions.Add(ColumnDefinition())
        self.DosesGrid.ColumnDefinitions.Add(ColumnDefinition())

        _logger.debug("DoseIndices loading")
        site_idx = DoseIndices[self.active_site]

        vol_range = site_idx.volumes

        _logger.debug("Updating ROI text")
        if self.roi_data is None:
            # Didn't get data back, likely we don't have dose calculated
            # Show the dose not calculated message and move on.
            _logger.debug("No roi_data, failed calculation. {self.roi_data=}")

            self.ROIVolume.Text = "--"

            # No indicies to be shown, but add the row definition for the
            # warning message
            indices = set()

            self.DosesGrid.RowDefinitions.Add(RowDefinition())

            roi_vol = None

            self.DosesGrid.Children.Add(self.ErrorBlock)

        else:
            self.ROIVolume.Text = f"{self.roi_data['ROIvol']:0.2f}"

            indices = site_idx.index_names & self.roi_data.keys()

            roi_vol = self.roi_data['ROIvol']

        for row, diname in enumerate(indices):

            self.DosesGrid.RowDefinitions.Add(RowDefinition())

            idx_header_label = IndexHeader(diname)
            self.DosesGrid.SetRow(idx_header_label, row + 1)

            self.DosesGrid.SetColumn(idx_header_label, 0)
            self.DosesGrid.Children.Add(idx_header_label)

            goal_value = BorderedTextBoxBlack(f'{self.roi_data[diname]:0.2f}')

            self.DosesGrid.SetRow(goal_value, row + 1)
            self.DosesGrid.SetColumn(goal_value, 1)
            self.DosesGrid.Children.Add(goal_value)

        for col, size in enumerate(vol_range):
            # Select the column with the correct size for PTV
            if roi_vol and vol_range[size][0] <= roi_vol < vol_range[size][1]:
                self.DosesGrid.SetColumn(self.ActiveVolume, col + 2)
                self.DosesGrid.Children.Add(self.ActiveVolume)

            self.DosesGrid.ColumnDefinitions.Add(ColumnDefinition())

            header_label = SizeBorderedHeader(size, vol_range[size])

            self.DosesGrid.SetRow(header_label, 0)
            self.DosesGrid.SetColumn(header_label, col + 2)
            self.DosesGrid.Children.Add(header_label)

            for row, diname in enumerate(indices):
                range_label = GoalBorderedText(site_idx[size][diname])

                self.DosesGrid.SetRow(range_label, row + 1)
                self.DosesGrid.SetColumn(range_label, col + 2)
                self.DosesGrid.Children.Add(range_label)


def show_indices_dialog(beamset, plan=None, casedata=None):
    indices_dialog = ConformityIndicesWindow(beamset, plan, casedata)
    result = indices_dialog.ShowDialog()
    return result
