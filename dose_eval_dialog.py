import logging

from math import inf
from System.Windows.Media import Brushes
from System.Windows.Controls import (Border, TextBlock, RowDefinition,
                                     ColumnDefinition, ComboBoxItem)
from System.Windows.Documents import Bold, Run, LineBreak

from .external import RayWindow

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


class Indices(dict):
    # Class to hold indices by site.

    volumes = None  # dict
    index_names = None  # dict

    def __init__(self):
        super().__init__(INDICES_DICT)

        self.volumes = {}
        self.index_names = {}

        for site, item in self.items():
            self.volumes[site] = {k: item[k]['Vol'] for
                                  k in sorted(item,
                                              key=lambda a: item[a]['Vol'][0])}

            self.index_names[site] = {index for indices in item.values()
                                      for index in indices if index != 'Vol'}


DoseIndices = Indices()


class MyWindow(RayWindow):
    active_site = "Brain"
    roi_data = None

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
                                       ElementName=PlanSelectPanel}"
                             Value="Collapsed">
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
                                Margin="{TemplateBinding Padding}"
                                Visibility="Collapsed"/>
                            <ToggleButton x:Name="HeaderSite"
                                DockPanel.Dock="Bottom"
                                IsChecked="{Binding IsExpanded, Mode=TwoWay,
                                            RelativeSource={RelativeSource
                                                            TemplatedParent}}"
                                Style="{StaticResource ExpanderButton}"/>
                        </DockPanel>
                        <ControlTemplate.Triggers>
                            <Trigger Property="IsExpanded" Value="true">
                                <Setter Property="Visibility"
                                        TargetName="ExpandSite"
                                        Value="Visible"/>
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>

    </Window.Resources>

    <StackPanel Background="#FFE6E6E6" MinHeight="20" Margin="0">
        <Expander Style="{StaticResource ExpanderPanel}">
            <DockPanel x:Name="PlanSelectPanel">
                <Label Content="Plan to evaluate: "/>
                <ComboBox />
            </DockPanel>
        </Expander>

        <DockPanel LastChildFill="False">
            <ComboBox x:Name="ROINameAndVol" DockPanel.Dock="Left">
                <ComboBoxItem Content="PTV50" IsSelected="True"/>
            </ComboBox>
            <StackPanel Orientation="Horizontal" DockPanel.Dock="Right">
                <Label Content="Site:"/>
                <ComboBox x:Name="Site">
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

                <Rectangle x:Name="ActiveVolume" Grid.RowSpan="4"
                           Grid.ColumnSpan="1" Grid.Column="2"
                           Panel.ZIndex="-1">
                    <Rectangle.Fill>
                        <SolidColorBrush
                         Color="{DynamicResource {x:Static
                         SystemColors.ActiveCaptionColorKey}}"/>
                    </Rectangle.Fill>
                </Rectangle>

            </Grid>
        </Border>
        <Button Name="btnCancel" IsCancel="true"
                Padding="0" Width="0" Height="0"/>
    </StackPanel>
</Window>
    """

    def __init__(self, casedata=None, plan=None, beamset=None):

        self.LoadComponent(self._XAML)

        # self.ROINameAndVol.Content = f'{roi_data["ROI"]} ({roi_data["ROIvol"]:0.1f} cc)'
        # self.Site.Content = f'{site}'

        self.roi_data = casedata

        # Build the list of sites and add the OnChanged Event Callback
        sites = DoseIndices.keys()
        self.build_site_dropdown(sites)
        self.Site.SelectionChanged += self.SiteChanged

        self.build_labels()

    def SiteChanged(self, sender, event):
        _logger.debug(f'Site change {sender.SelectedItem.Content=}'
                      f' {self.active_site=}')
        if sender.SelectedItem.Content != self.active_site:
            self.active_site = sender.SelectedItem.Content
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
        site = self.active_site
        roi_data = self.roi_data

        vol_range = DoseIndices.volumes[site]

        indices = DoseIndices.indexs[site] & roi_data.keys()

        self.DosesGrid.Children.Clear()

        self.DosesGrid.RowDefinitions.Clear()
        self.DosesGrid.RowDefinitions.Add(RowDefinition())

        self.DosesGrid.ColumnDefinitions.Clear()
        self.DosesGrid.ColumnDefinitions.Add(ColumnDefinition())
        self.DosesGrid.ColumnDefinitions.Add(ColumnDefinition())

        for row, index in enumerate(indices):

            self.DosesGrid.RowDefinitions.Add(RowDefinition())

            idx_header_label = IndexHeader(index)

            self.DosesGrid.SetRow(idx_header_label, row + 1)
            self.DosesGrid.SetColumn(idx_header_label, 0)
            self.DosesGrid.Children.Add(idx_header_label)

            goal_value = BorderedTextBoxBlack(f'{roi_data[index]:0.2f}')

            self.DosesGrid.SetRow(goal_value, row + 1)
            self.DosesGrid.SetColumn(goal_value, 1)
            self.DosesGrid.Children.Add(goal_value)

        for col, size in enumerate(vol_range):
            # Select the column with the correct size for PTV
            if vol_range[size][0] <= roi_data['ROIvol'] < vol_range[size][1]:
                self.DosesGrid.SetColumn(self.ActiveVolume, col + 2)
                self.DosesGrid.Children.Add(self.ActiveVolume)

            self.DosesGrid.ColumnDefinitions.Add(ColumnDefinition())

            header_label = SizeBorderedHeader(size, vol_range[size])

            self.DosesGrid.SetRow(header_label, 0)
            self.DosesGrid.SetColumn(header_label, col + 2)
            self.DosesGrid.Children.Add(header_label)

            for row, index in enumerate(indices):
                range_label = GoalBorderedText(DoseIndices[site][size][index])

                self.DosesGrid.SetRow(range_label, row + 1)
                self.DosesGrid.SetColumn(range_label, col + 2)
                self.DosesGrid.Children.Add(range_label)
