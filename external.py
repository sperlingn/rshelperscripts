from enum import IntEnum
import sys
from copy import deepcopy
import logging as _logging
from uuid import uuid4
from dataclasses import dataclass
from collections.abc import MutableMapping
from typing import Type
from zlib import decompress as zlibdecompress
from base64 import b64decode
from .mock_objects import MakeMockery
_logger = _logging.getLogger(__name__)


__opts = {'DUP_MAX_RECURSE': 10}

_NAMELIST = ['Name', 'DicomPlanLabel', 'SegmentNumber']

_INDIRECT_MACHINE_REF = {}


def helperoverride(function):
    function.__overridden__ = True
    return function


try:
    from System.Windows import (MessageBox as _MessageBox, WindowStyle,
                                SizeToContent, Window, Visibility, Rect,
                                DragDrop, DragDropEffects, DragDropKeyStates)
    from System.Windows.Controls import (Button, TextBlock, DockPanel, Label,
                                         ListBoxItem, TextBox, Image, ToolTip,
                                         Slider, Dock, Orientation)
    from System.Windows.Shapes import Rectangle
    from System.Windows.Media import (VisualBrush, Brushes, VisualTreeHelper,
                                      PixelFormats, DrawingVisual)
    from System.Windows.Media.Imaging import RenderTargetBitmap
    from System import (Double as SystemDouble,  # noqa: W0611
                        Array as SystemArray,
                        DateTime)
    from System import ArgumentOutOfRangeException, InvalidOperationException
    from System.IO import InvalidDataException
    from System.Windows.Input import Keyboard, ModifierKeys, MouseButtonState
    from System.Windows.Markup import XamlWriter, XamlReader
    from System.IO import StringReader
    from System.Xml import XmlReader

    from win32api import GetCursorPos

    ValScale = {getattr(ModifierKeys, 'None'): 1,
                ModifierKeys.Control: 5,
                ModifierKeys.Shift: 10,
                ModifierKeys.Control | ModifierKeys.Shift: 50}

except ImportError as e:

    _logger.error(f"{e}")

    # TODO: Work to include a QT or other based dialog? Right now we can assume
    # that the Windows MessageBox will work for RS.  This is only for debugging
    # functions.
    @helperoverride
    class _MessageBox:
        def Show(*args, **kwargs):
            _logger.info("MessageBox: args={}, kwargs={}", args, kwargs)
            return True

    @helperoverride
    class ArgumentOutOfRangeException(IndexError):
        pass

    @helperoverride
    class InvalidOperationException(Exception):
        pass

    @helperoverride
    class InvalidDataException(ValueError):
        pass

    @helperoverride
    class Button:
        def __init__(self, *args, **kwargs):
            raise NotImplementedError("Only supported for CLR launch.")


class _CompositeActionDummy():
    _name = ""

    def __init__(self, *args, **kwargs):
        if 'name' in kwargs:
            self._name = kwargs['name']
        elif len(args) > 0:
            self._name = args[0]

    def __enter__(self):
        _logger.info("Entered {} Undo state.".format(self._name))
        return self

    def __exit__(self, e_type, e, e_traceback):
        if e_type is not None:
            _logger.exception('{!s}'.format(e))

        _logger.info("Exited  {} Undo state.".format(self._name))


class MB_Button(IntEnum):
    OK = 0
    OKCancel = 1
    YesNo = 4
    YesNoCancel = 3


class MB_Icon(IntEnum):
    Asterisk = 64
    Error = 16
    Exclamation = 48
    Hand = 16
    Information = 64
    None_ = 0
    Question = 32
    Stop = 16
    Warning_ = 48


class MB_Result(IntEnum):
    Cancel = 2
    No = 7
    None_ = 0
    OK = 1
    Yes = 6

    def __bool__(self):
        # Only return True for OK and Yes results.  Otherwise consider it a
        # No/False/Cancel result for bool check.
        return self in (MB_Result.OK, MB_Result.Yes)


class MB_Options(IntEnum):
    DefaultDesktopOnly = 131072
    None_ = 0
    RightAlign = 524288
    RtlReading = 1048576
    ServiceNotification = 2097152


def _Show_MB(message, caption="Message", *args, ontop=False):
    opt = MB_Options.DefaultDesktopOnly if ontop else MB_Options.None_
    res = _MessageBox.Show(f"{message}", f"{caption}", *args, opt)
    try:
        return MB_Result(res)
    except ValueError:
        # New return type, just return it and log so we can add it later.
        _logger.warning(f'Unexpected message box result: {res}')
        return res


def Show_OK(message, caption="OK", ontop=False, icon=MB_Icon.None_,
            defaultResult=MB_Result.None_):
    button = MB_Button.OK
    return _Show_MB(message, caption, button, icon, defaultResult, ontop=ontop)


def Show_Warning(message, caption="Warning", ontop=True):
    return Show_OK(message, caption, ontop, icon=MB_Icon.Warning_)


def Show_OKCancel(message, caption="OK or Cancel?", ontop=False,
                  icon=MB_Icon.None_, defaultResult=MB_Result.None_):
    button = MB_Button.OKCancel
    return _Show_MB(message, caption, button, icon, defaultResult, ontop=ontop)


def Show_YesNo(message, caption="Yes or No?", ontop=False, icon=MB_Icon.None_,
               defaultResult=MB_Result.None_):
    button = MB_Button.YesNo
    return _Show_MB(message, caption, button, icon, defaultResult, ontop=ontop)


def Show_YesNoCancel(message, caption="Yes, No, or Cancel?", ontop=False,
                     icon=MB_Icon.None_, defaultResult=MB_Result.None_):
    button = MB_Button.YesNoCancel
    return _Show_MB(message, caption, button, icon, defaultResult, ontop=ontop)


def _await_user_input_mb(message):
    _logger.debug(f'Waited for user input: "{message}"')
    return Show_OK(f'{message}', "Awaiting Input", ontop=True)


try:
    from connect import RayWindow
except ImportError:
    try:
        import wpf

        class RayWindow(Window):
            def LoadComponent(self, XAML):
                return wpf.LoadComponent(self, XAML)
    except ImportError:
        class RayWindow():
            def LoadComponent(self, XAML):
                raise NotImplementedError("Neither RS nor wpf in environment")


try:
    from connect import (get_current, CompositeAction as _CompositeActionOrig,
                         await_user_input as _await_user_input, set_progress)

    IN_RAYSTATION = True
    RS_VERSION = get_current("ui").GetApplicationVersion()

except ImportError:
    # Replacement functions when not running in RS
    IN_RAYSTATION = False
    RS_VERSION = "0.0"

    from .mock_objects import MockPatient

    def get_current(name):
        # TODO: Might want to return a sample object that has reasonable
        # facimiles of the real objects for debugging.
        if name == 'Patient':
            return MockPatient()
        elif name == '':
            return None
        else:
            return None

    class _CompositeActionOrig(_CompositeActionDummy):
        pass

    _await_user_input = _await_user_input_mb

    def set_progress(message, percent):
        _logger.info(f"Progress: {message} ({percent:.0%})")

finally:

    @helperoverride
    class CompositeAction:
        _clsinstance = None
        _instance = None
        _blocked = False
        my_args = None
        _dummyclass = _CompositeActionDummy
        _realclass = _CompositeActionOrig

        def __init__(self, *args, **kwargs):
            self.my_args = (args, kwargs)
            self.instance

        @property
        def instance(self):
            cls = type(self)
            if not self._instance:
                (args, kwargs) = self.my_args
                if cls._blocked:
                    self._instance = cls._dummyclass(*args, **kwargs)
                elif cls._clsinstance and cls._clsinstance != self:
                    self._instance = cls._dummyclass(*args, **kwargs)
                else:
                    self._instance = cls._realclass(*args, **kwargs)
                    cls._clsinstance = self

            return self._instance

        @classmethod
        def block(cls):
            cls._blocked = True

        @classmethod
        def unblock(cls):
            cls._blocked = False

        @classmethod
        @property
        def isactive(cls):
            return cls._clsinstance is not None

        @classmethod
        def get_active_singleton(cls):
            return cls._clsinstance

        @property
        def is_root(self):
            return self == type(self)._clsinstance

        @property
        def is_fake(self):
            return not self.is_root

        def __enter__(self):
            self.instance.__enter__()
            return self

        def __exit__(self, e_type, e, e_traceback):
            cls = type(self)
            if e_type is not None:
                _logger.exception(str(e))

            if self == cls._clsinstance and not cls._blocked:
                # We were the first launch of CompositeAction, we can now clear
                # the class instance and let a new one start next time.
                cls._clsinstance = None

            # Use the private instance so we don't create a new one
            # accidentally (will throw an Error if _instance is None because we
            # have exited twice without entering
            self._instance.__exit__(e_type, e, e_traceback)

            # Make sure that we don't reuse this instance later, if we run
            # __enter__ again, it will generate a new self._instance following
            # the logic in instance(self)
            self._instance = None

            return None

    class SuspendCompositeAction:
        _clsinstance = None
        _CompositeActionClass = CompositeAction
        active_action_args = None
        message = "Suspending composite action"

        def __init__(self, reason=None):
            if not type(self)._clsinstance:
                # First time being used.
                type(self)._clsinstance = self

            if reason:
                self.message = f"{self.message}: ({reason})"

        def __enter__(self):
            cls = type(self)
            ca_class = cls._CompositeActionClass
            ca_class.block()
            if ca_class.isactive:
                # Currently in a CompositeAction, suspend it.
                _logger.info(f"{self.message}")
                self.active_ca_wrapper = ca_class.get_active_singleton()
                # Exit the composite action without an error.
                self.active_ca_wrapper.__exit__(None, None, None)

            return None

        def __exit__(self, e_type, e, e_traceback):
            cls = type(self)
            if e_type is not None:
                _logger.exception(f"Reached exit of {self.__class__.__name__}"
                                  " with an error, bubble up.")
                raise e

            if self == cls._clsinstance:
                # We were the first launch of SuspendCompositeAction, we can
                # now clear the class instance and let a new one start.
                cls._clsinstance = None

                # Unblock CompositeAction from being created.
                ca_class = cls._CompositeActionClass
                ca_class.unblock()

                if self.active_ca_wrapper:
                    # There was a running CompositeAction when we halted, start
                    # it again with the same arguments
                    self.active_ca_wrapper.instance.__enter__()
                    self.active_ca_wrapper = None

            return None

    @helperoverride
    def await_user_input(msg):
        # Wrapper to prevent await_user_input from spawning during a composite
        # action context manager.

        if CompositeAction._clsinstance is not None:
            # Log a warning (include traceback info to help trace cause)
            _logger.warning("Tried to call await_user_input during a composite"
                            " action.  This leads to a crash. Ignoring call.\n"
                            "Message was: '{}'".format(msg), exc_info=True)
            _await_user_input_mb(msg)
        else:
            _await_user_input(msg)

try:
    from pydicom import dcmread, uid
except ImportError:
    # If we don't have pydicom in this env, can't do any of this. Just return a
    # dummy function that returns a usuable but empty dataset like object.
    class _DUMMY_DCM:
        Modality = 'CT'

        def __getattr__(self, attr):
            # Suppress AttributeErrors in favor of empty returns.  Only usefuly
            # because this is a dummy class for debugging or when running
            # without dcmread.
            return None

    @helperoverride
    def dcmread(*args, **kwargs):
        DUMMY_DCM = _DUMMY_DCM()
        return DUMMY_DCM

    @helperoverride
    class uid:

        @staticmethod
        def generate_uid(prefix=None, entropy_sources=[]):
            # Very short and not entirely compliant UID generator

            uid = uuid4().int
            if prefix:
                prefix = f'{prefix}'[0:32]
                prefix[31] = '0'
                return f'{prefix}.{uid}'[0:62]

            return f'2.25.{uid}'[0:62]


def rs_hasattr(obj, attrname):
    try:
        if '.' in attrname:
            # Composite attribute, nest.
            firstattr, rest = attrname.split('.', 1)
            return rs_hasattr(rs_getattr(obj, firstattr), rest)
        return hasattr(obj, attrname)
    except (KeyError, ValueError, IndexError, TypeError):
        return False


def rs_getattr(obj, attrname, *args, **kwargs):
    if attrname in ['', '.', 'self']:
        # If we are passed an empty attrname, a bare dot, or self, return obj
        return obj

    if rs_hasattr(obj, attrname) and '.' in attrname:
        # Composite attribute, nest.
        firstattr, rest = attrname.split('.', 1)
        return rs_getattr(getattr(obj, firstattr), rest, **kwargs)
    return getattr(obj, attrname, *args, **kwargs)


def rs_callable(obj, attrname):
    try:
        return callable(getattr(obj, attrname))
    except (AttributeError, ValueError, KeyError, IndexError):
        return False


def get_module_opt(opt_name, default=None):
    mod_opts = sys.modules[__name__].__opts

    return mod_opts[opt_name] if opt_name in mod_opts else default


def set_module_opt(opt_name, value):
    mod_opts = sys.modules[__name__].__opts
    mod_opts[opt_name] = value


def set_module_opts(**kwargs):
    for opt, val in kwargs.items():
        set_module_opt(opt, val)


class IndirectInheritanceClass:
    # Class to act like we inherited from the base class of the object passed,
    # and extended, without subclassing.  Allows attribute access for the
    # passed object but nothing else.

    _base = None

    def __new__(cls, *args, **kwargs):
        inst = super().__new__(cls)
        if len(args) > 0:
            inst._base = args[0]
        return inst

    def __getattr__(self, attr):
        return getattr(self._base, attr)


def StaticMWHandler_IncDecScroll(caller, event):
    try:
        scale = ValScale.get(Keyboard.Modifiers, 1)
        valdelta = int(event.Delta * scale / 120.)

        if hasattr(caller, "Value"):
            caller.Value += valdelta
        elif hasattr(caller, "Text"):
            caller.Text = '%d' % (int(caller.Text) + valdelta)

    except ValueError:
        pass
    except Exception as ex:
        _logger.exception(ex)


class ListItemPanel(DockPanel):
    _button = None
    _label = None

    def __init__(self, obj_name_in, button_click, index,
                 is_current=False, is_default=False, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._button = Button()
        _logger.debug(f"{obj_name_in=}")
        if is_current:
            self._button.Tag = 'current'
        if is_default:
            self._button.IsDefault = True

        # Use a TextBlock to get around _ being an accelerator in buttons.
        obj_text = TextBlock()
        obj_text.Text = f"{obj_name_in}"
        self._button.Content = obj_text

        self._button.Click += button_click

        self._label = Label()
        self._label.Content = f"_{index}"
        self._label.Target = self._button

        self.Children.Add(self._label)
        self.Children.Add(self._button)


class ListSelectorDialog(RayWindow):
    _XAML = """
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        xmlns:d="http://schemas.microsoft.com/expression/blend/2008"
        xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
        xmlns:System="clr-namespace:System;assembly=mscorlib"
        Title="Select List"
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
        </Style>
        <Style TargetType="{x:Type Label}">
            <Setter Property="VerticalAlignment" Value="Center"/>
        </Style>
        <Style TargetType="{x:Type Button}">
            <Setter Property="Margin" Value="5"/>
            <Setter Property="Padding" Value="5"/>
            <Style.Triggers>
                <Trigger Property="Tag" Value="current">
                    <Setter Property="BorderThickness" Value="3" />
                    <Setter Property="BorderBrush">
                        <Setter.Value>
                            <RadialGradientBrush RadiusX="1" RadiusY="1">
                                <GradientStop Color="#FF04B6D3" Offset="0.34"/>
                                <GradientStop Color="White" Offset="1"/>
                            </RadialGradientBrush>
                        </Setter.Value>
                    </Setter>
                </Trigger>
            </Style.Triggers>
        </Style>
    </Window.Resources>
    <Window.TaskbarItemInfo>
        <TaskbarItemInfo ProgressState="Normal" ProgressValue="50"/>
    </Window.TaskbarItemInfo>

    <StackPanel Background="#FFE6E6E6" MinHeight="20" Margin="0">
        <Label x:Name="PickerLabel" Content="Select one:"/>
        <StackPanel x:Name="ListPanel">
        </StackPanel>
    </StackPanel>
</Window>
    """
    ListPanel = None  # StackPanel
    _results = None  # dict for results
    _list_in = None  # list of list_in

    def __init__(self, list_in, results):
        self.LoadComponent(self._XAML)

        if 'description' in results:
            self.PickerLabel.Content = results['description']

        self.ListPanel.Children.Clear()

        self._list_in = {obj_name(obj): obj for obj in list_in}

        self._results = results

        _logger.debug(f"{results=}")
        for i, obj_name_in in enumerate(self._list_in):
            is_current = self.obj_matches('current', obj_name_in)
            is_default = self.obj_matches('default', obj_name_in)
            obj_listitem = ListItemPanel(obj_name_in, self.List_Click,
                                         i+1, is_current, is_default)

            self.ListPanel.Children.Add(obj_listitem)
            continue

            obj_button = Button()
            _logger.debug(f"{obj_name_in=}")
            if self.obj_matches('current', obj_name_in):
                obj_button.Tag = 'current'
            if self.obj_matches('default', obj_name_in):
                obj_button.IsDefault = True

            # Use a TextBlock to get around _ being an accelerator in buttons.
            obj_text = TextBlock()
            obj_text.Text = f"{obj_name_in}"
            obj_button.Content = obj_text

            obj_button.Click += self.List_Click
            self.ListPanel.Children.Add(obj_button)

    def obj_matches(self, feature, obj_name_in):
        if feature not in self._results:
            return False

        if self._results[feature] in [obj_name_in, self._list_in[obj_name_in]]:
            _logger.debug(f"Found {feature} {obj_name_in=}")
            return True
        elif isinstance(self._results[feature], str):
            # This was a simple check, not present, so false.
            return False

        try:
            for matcher in self._results[feature]:
                if matcher in [obj_name_in, self._list_in[obj_name_in]]:
                    return True
        except (IndexError, ValueError, TypeError):
            return False

        return False

    def List_Click(self, caller, event):
        try:
            text_child = caller.Content.Text
            self._results['Selected'] = self._list_in[text_child]
            self.DialogResult = True
        finally:
            self.Close()


class MLCRenderTextBox(TextBox):
    StyleXAML = """
    <ResourceDictionary xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
             xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation">
        <Style x:Key="MLCTemplate" TargetType="{x:Type TextBox}">
            <Setter Property="Template">
                <Setter.Value>
<ControlTemplate TargetType="{x:Type TextBox}">
    <Border Background="White" BorderBrush="Black" BorderThickness="1">
        <Viewbox Width="{TemplateBinding Width}"
                Height="{TemplateBinding Height}" ClipToBounds="True">
        <Canvas Width="40" Height="40" Background="White"
                RenderTransformOrigin="0.5,0.5">
            <Canvas.RenderTransform>
                <TransformGroup>
                    <ScaleTransform ScaleX="{Binding
    RelativeSource={RelativeSource TemplatedParent}, Path=FontSize}"
                                    ScaleY="{Binding
    RelativeSource={RelativeSource TemplatedParent}, Path=FontSize}"/>
                    <SkewTransform/>
                    <RotateTransform Angle="{Binding Tag[4],
                        RelativeSource={RelativeSource TemplatedParent}}"/>
                    <TranslateTransform/>
                </TransformGroup>
            </Canvas.RenderTransform>
            <Canvas.Clip>
                <RectangleGeometry Rect="0,0,40,40"/>
            </Canvas.Clip>
            <TextBlock x:Name="TemplateJawsPoints" Visibility="Collapsed" >
                <TextBlock.Text>
<MultiBinding StringFormat="{}{0},{3} {1},{3} {1},{2} {0},{2} {0},{3}">
    <Binding RelativeSource="{RelativeSource TemplatedParent}" Path="Tag[0]"/>
    <Binding RelativeSource="{RelativeSource TemplatedParent}" Path="Tag[1]"/>
    <Binding RelativeSource="{RelativeSource TemplatedParent}" Path="Tag[2]"/>
    <Binding RelativeSource="{RelativeSource TemplatedParent}" Path="Tag[3]"/>
</MultiBinding>
                </TextBlock.Text>
            </TextBlock>
            <Rectangle Width="40" Height="40" Panel.ZIndex="1">
                <Rectangle.Fill>
                    <SolidColorBrush Color="#FF5EB6FF" Opacity="0.8"/>
                </Rectangle.Fill>
                <Rectangle.Clip>
<GeometryGroup>
    <RectangleGeometry Rect="0,0,40,40"/>
    <PathGeometry>
        <PathGeometry.Figures>
            <PathFigure IsClosed="True">
                <PolyLineSegment Points="{Binding Text,
                    ElementName=TemplateJawsPoints}" />
            </PathFigure>
        </PathGeometry.Figures>
        <PathGeometry.Transform>
            <TransformGroup>
                <ScaleTransform ScaleY="-1" ScaleX="1"/>
                <TranslateTransform X="20" Y="20"/>
            </TransformGroup>
        </PathGeometry.Transform>
    </PathGeometry>
</GeometryGroup>
                </Rectangle.Clip>
            </Rectangle>
<Polygon Fill="#FF005DFF" Canvas.Left="20" Canvas.Top="20"
       Points="{Binding Text, RelativeSource={RelativeSource TemplatedParent}}"
       Stroke="#FF80C5FF" StrokeThickness="0.2" StrokeLineJoin="Bevel">
    <Polygon.RenderTransform>
        <TransformGroup>
            <ScaleTransform ScaleY="-1" ScaleX="1"/>
            <SkewTransform AngleY="0" AngleX="0"/>
            <RotateTransform Angle="0"/>
            <TranslateTransform/>
        </TransformGroup>
    </Polygon.RenderTransform>
</Polygon>
<Path x:Name="Crosshair" Canvas.Left="20" Canvas.Top="20" Stroke="Blue"
      StrokeThickness="0.1" Data="M 0,-20 v40 M -20,0 h40
M-1,-20 h2 m-2,5 h2 m-2,5 h2 m-2,5 h2 m-2,10 h2 m-2,5 h2 m-2,5 h2 m-2,5 h2
M-20,-1 v2 m5,-2 v2 m5,-2 v2 m5,-2 v2 m10,-2 v2 m5,-2 v2 m5,-2 v2 m5,-2 v2
M-.5,-19 h1 m-1,1 h1 m-1,1 h1 m-1,1 h1 m-1,2 h1 m-1,1 h1 m-1,1 h1 m-1,1 h1
    m-1,2 h1 m-1,1 h1 m-1,1 h1 m-1,1 h1 m-1,2 h1 m-1,1 h1 m-1,1 h1 m-1,1 h1
    m-1,2 h1 m-1,1 h1 m-1,1 h1 m-1,1 h1 m-1,2 h1 m-1,1 h1 m-1,1 h1 m-1,1 h1
    m-1,2 h1 m-1,1 h1 m-1,1 h1 m-1,1 h1 m-1,2 h1 m-1,1 h1 m-1,1 h1 m-1,1 h1
M-19,-.5 v1 m1,-1 v1 m1,-1 v1 m1,-1 v1 m2,-1 v1 m1,-1 v1 m1,-1 v1 m1,-1 v1
    m2,-1 v1 m1,-1 v1 m1,-1 v1 m1,-1 v1 m2,-1 v1 m1,-1 v1 m1,-1 v1 m1,-1 v1
    m2,-1 v1 m1,-1 v1 m1,-1 v1 m1,-1 v1 m2,-1 v1 m1,-1 v1 m1,-1 v1 m1,-1 v1
    m2,-1 v1 m1,-1 v1 m1,-1 v1 m1,-1 v1 m2,-1 v1 m1,-1 v1 m1,-1 v1 m1,-1 v1"/>
        </Canvas>
    </Viewbox>
    </Border>
</ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>
    </ResourceDictionary>
    """

    def __init__(self, segment, layer, *args,
                 isTT=False, scale=1.0, Height=None, Width=None, **kwargs):
        super().__init__(*args, **kwargs)

        res = XamlReader.Load(XmlReader.Create(StringReader(self.StyleXAML)))
        self.Style = res["MLCTemplate"]

        if Height is not None:
            self.Height = Height
        if Width is not None:
            self.Width = Width

        if isTT:
            self.Tag = segment
            self.Text = layer
            self.FontSize = scale
            self.Width = self.Height = 200
            return

        try:
            mlc_points = self.get_mlc_polygon(segment, layer)
        except TypeError:
            _logger.error(f"Couldn't build MLC polygon:\n{layer=} {segment=}",
                          exc_info=True)
            mlc_points = ''

        tag_data = [*segment.JawPositions, -segment.CollimatorAngle]

        self.Tag = SystemArray[SystemDouble](tag_data)
        self.Text = f'{mlc_points}'

        # Zoom in for MLC banks less than 40cm tall.
        zoom = 40. / (layer.LeafCenterPositions[-1]
                      - layer.LeafCenterPositions[0]
                      + (layer.LeafWidths[-1] / 2)
                      + (layer.LeafWidths[0] / 2))
        self.FontSize = scale * zoom

        mlc_TT = ToolTip()
        mlc_TT_tb = self.__class__(self.Tag, self.Text, *args,
                                   isTT=True, Height=400, Width=400,
                                   scale=zoom, **kwargs)
        mlc_TT.Content = mlc_TT_tb

        self.ToolTip = mlc_TT

    @staticmethod
    def get_mlc_polygon(segment, layer):
        LEAF_LEN = 15.5

        pts_bank0 = []
        pts_bank1 = []
        for lcp, lwidth, lp_bank0, lp_bank1 in zip(layer.LeafCenterPositions,
                                                   layer.LeafWidths,
                                                   *segment.LeafPositions):

            # Note: We can chose to render based on the actual leaf size,
            #  or run the leaf all the way back to -20...

            pts_bank0 += [(lp_bank0 - LEAF_LEN, lcp - lwidth/2),
                          (lp_bank0, lcp - lwidth/2),
                          (lp_bank0, lcp + lwidth/2),
                          (lp_bank0 - LEAF_LEN, lcp + lwidth/2)]

            pts_bank1 += [(lp_bank1 + LEAF_LEN, lcp - lwidth/2),
                          (lp_bank1, lcp - lwidth/2),
                          (lp_bank1, lcp + lwidth/2),
                          (lp_bank1 + LEAF_LEN, lcp + lwidth/2)]

        top_b0 = (-20, pts_bank0[0][1])
        bot_b0 = (-20, pts_bank0[-1][1])

        top_b1 = (20, top_b0[1])
        bot_b1 = (20, bot_b0[1])

        pt_list = [top_b0,
                   *pts_bank0,
                   bot_b0,
                   top_b0,
                   top_b1,
                   *pts_bank1,
                   bot_b1,
                   top_b1,
                   top_b0]

        return ' '.join([','.join(map(str, pt)) for pt in pt_list])


class GantryRenderSlider(Slider):
    StyleXAML_enc = """
eJztXW1z4jgS/j6/QuX9uhZ+BZOCrZokl8ndbW6mAkX2PnpBAVWMzRnDkN2a/36tFxsbkmAMyu3M
KUwCkqV+ulstqVvuMR8Q/PTuyTJZpWNyTccZTeIwfUabeRQvLzZ9Y5Zli4tWazmekXm4xHM6TpNl
8pjhcTJvfaXx46blWFa7tQnnkfEBlX84jeMotBYpWZI4Cxkfxi8Fvd4ge44I2lz8kzz3jU9hnKXP
92RhoGGYTkk2fF6QvvHn5oJ9QIOITkj6rdRdkCBZRlL0JU0WJM2AzE0SZwP6BzHQKIxWQMDGRutQ
pyGZL6IwIzvUS40xp7Z/mTe5Asw0iXIqR/BfITOi5OvvyQY90Ek2g545vUsaT2g8FfXfDHRL6HSW
vdBAXIAWVxFdDJPLZBVPYKyG6eolyaoihPE6XObQrmVZWxxRugzHT9OUkewbDzP6orJeI7u5+Fc4
B2VcXT2IYTbeQronMahqmIbx8jFJ559TOqVx37Cw/zP81oAtQeMdYvU6cwJFn08g9aJ+R955MA4j
UlBoHdv7iXxt3Pk+gZm2xUYf42nEDDG3kjsa0/lq/jPoGYyHrsmArxP9P6tllFvX5EuYwuz99m13
Hh3khPMQlZk5gkKv1WQAeq1Txv3wNDiCf0nrLNa8Q7S5VReETrHugshJVr6lcoK1F0R2rL4pmX2T
Rb/BHuIzQ/h332jDewPSzWx52/sco977EmYzNICN6okMZ3T8FJMlbA62Iet+pTH5R8JM85KsSZRX
D7Iwzdi1q3DRNwb/WcFikF/7WzzZvdJAN4wvfEOjqOGQMRbC9FMaTigsU5fpajlDwNkXkAVmrQWz
zGEMgxiyyuZVzdBeQ8R5aZAli2Vz2px+mdZVEkWEe3CnEd0jjIBykvaNn25uLvnLQJ8fH5eE6ayJ
jdcFEz8lMFgEFcLtymafCtZrnXt4ei1FBvUi4Sar1wlTVEzv6zALG8rA+n8iyZyA24hu6HQFwUTf
mCPT8y3k2T6aIQcHLgqw5zvIdnG3YyO7i13bRo6HPfjbxY7lINfFbaeN3A68BdAT2z6UutDCQx7u
QGevDZfgDUh14a0LlegWWWgNvzPkW9gNPFmdt5E9ePeclqQscCSq5EEwJLmTvArGuQxrZDoglekj
07Vx2+4AcAR12Aq6yLSxB53NNna8Di/ZLrwBV17Aii6r9LALxFjJbsNbgB3HY0WHtXFs3HV8VgTK
gIQ9cdEKgKwT4HYAfSzcZUWGHzisGHQAxvW48FDsgGym28addocV2y40cgMcWAEr+hY09izsMYaB
tXaAfkXdAHcCy0e2LfRp5hUgG2ir0/V8BEuyaxddRc+criQrQXNMwVHOkGBXcitlkaJIQXM5hRKE
DqSCpH6k9nLlCc0KxQqlS52L8RDDwWxDjpWPYPCauQcNJ4no2MiFPOSXbmO2h49pmnyFeJou6e80
oixgvqWTCYmb7vbSfYCYPyVAZd8p8cDbYtroG3egbctCfmChj8gGD1z8YS+Y2PCpqUdWiw+bMbLv
6wxTGrKgasukDWuB3+0AjxY6kbvc22vu3fWN6zB9GjAvFlZ+iLX/ek4ZGBk4nnfhYgER6V0yAZ7z
6FOeW0D9ZbKpOm7cNk9x3F7xEYJr9jqTj/AiiDgwaRqU/AjbeL6FnxBuFnzsuwN3yIPZBi6Bj0aw
GbBtxmQ1I1F3yy6fNKhvwgKexTc3My/OUKAK0BdQVeDbYo/1mm1BB3HNHPh2u31z54QzYnOvBRoo
QZ9vFQsekudwXNgHEPs4YzuCEpF9icmtZ4ssgZXIySE9LifDlGJyYPZBEapZTJ5Cq2tRKaQ1VeGy
LVK48GdxwJnSoJ2ZD5das9idiaoMcb6de76cajMxUBFSNuWEmHY7X0+jfHoj/k+NmDmkXEzMXNw1
86XeAZIZTSnuqoRdlairEnRVY65qyFWJuKoBVzXeqoZb1WirGmxVY63dUMusxlrccsTYKRo0bppt
YRbFqG23owhVA7xKfFcJ7yrRXSW4q8R2ldCuEtmVA7tKXFcJ68pRXTmo243pRkwqZWs8M7kZV9Wa
2R2fyCcdgx1YO9p+DsRNgS+mSlYNsZ7fqnVDBISiFaE8gb730wk1Q7BznKPIjipurZKhLsvx/a1S
SlSSO2TMk1IyrhyAR2Tm++zp7+GpvFfApXwDV+pISnmURsUqF4ytJKq2t9JuPVNnVxXHXq3pmjJW
epeoSOE+lB8/vMeJjvpjKvXh4nvE3eomBwMZ8WMYRbOjOFdicErHWxyDqj8dU4fguSptqjj4Uqao
vdM1JWdpJWXlaAptl8uibmkvTZGROlGqNwzUrlgqhyQPiEfIhqjDDVy1cbdKmNKJ8CkBSK914s2m
d7sff9y93vqtj2i5k6Et0rOvHnSC9tu9lSZohxudoP1Kb52gfRQRnaBdk6xO0H6bL52gXaavE7TV
yaYTtL+zzC6doK0TtP+6t0D/DxK0VWZo35PJgfzs19KzLRHMnyU/+2UuamdnmyI9OyilZzfnTudn
6/zsHYo/wi6u87PPBKjzs3V+9plRdX52fa51frbOz9b52To/u7nGdH72CfR1frbOzz4Phs7P1vnZ
54HQ+dlvCqLzs+si6Pzs+ig6P/soDJ2fXQtD52fXhtD52bUwdH52Yxidn11LDp2fvUtd52fXanm4
Va8lnxn+RpOdh5PjYUqnU5Iewr5bRRmVbWsIVG6OAXJCWcpVXcUVHUrPZP/78pqmInPrnqyBYZYD
IJ/pfhNGy9q3a1+k/jmlxRPpc6q3SUr/AG2FUR3SvVZjmfMH0IvnxO88Zm/L4zado2CRV0UHRa/y
9j2PNH92/Y810P+7kZatDmhnBJfoGHTTTL7t/yB5Uz6Zn3RQvIOSwSp51Aq3136/Wa/1+pc+5Ne2
tVDDvsdCVPRa+9+78cuH/wJhdzbL
    """
    StyleXAML = zlibdecompress(b64decode(StyleXAML_enc)).decode('UTF-8')

    def __init__(self, beam, *args,
                 isTT=False, Height=None, Width=None, **kwargs):
        super().__init__(*args, **kwargs)

        res = XamlReader.Load(XmlReader.Create(StringReader(self.StyleXAML)))
        self.Style = res["GantryRep"]

        self.IsDirectionReversed = beam.ArcRotationDirection != 'Clockwise'

        angles = [180 - (180 - angle) % 360 for angle in
                  [beam.GantryAngle, beam.ArcStopGantryAngle]
                  if angle is not None]

        self.Minimum = min(angles)
        self.Maximum = max(angles)

        if beam.ArcStopGantryAngle is None:
            self.Orientation = Orientation.Vertical

        if Height is not None:
            self.Height = Height
        if Width is not None:
            self.Width = Width

        if not isTT:
            gantry_TT = ToolTip()
            gantry_TT.Content = self.__class__(beam, *args,
                                               isTT=True,
                                               Height=400,
                                               Width=400, **kwargs)
            self.ToolTip = gantry_TT


class GenericReorderDialog(RayWindow):
    _XAML = None

    ItemListBox = None  # ListBox
    BeamNumbers = None  # StackPanel
    BtnOK = None  # Button (OK)
    FirstBeamNo = None  # Text
    _results = None  # dict for results
    _list_in = None  # list of list_in
    _dragstartpoint = None  # When dragging, screen coordinates of start

    # C.f. https://stackoverflow.com/a/27975085
    _dragdropwindow = None  # Preview window of object being drug

    def __init__(self, list_in, results):
        self.LoadComponent(self._XAML)

        self.ItemListBox.Items.Clear()
        self.ItemNumbers.Children.Clear()

        self.ItemListBox.PreviewMouseMove += self.ReorderDlgPreviewMouseMove
        self.ItemListBox.Drop += self.ItemListBox_Drop

        self._list_in = {obj_name(obj): obj for obj in list_in}

        self.AddItemsToListBox(self._list_in)

        self.BtnOK.Click += self.OK_Click

        self._results = results

        _logger.debug(f"{results=}")

    @staticmethod
    def BuildLBI(item_name, item):
        lbi = ListBoxItem()
        lbi.Tag = f"{item}"
        lbi.Content = f"{item_name}"
        return lbi

    @property
    def lowest_n(self):
        return 0

    def AddItemsToListBox(self, itemdict):
        lowest_n = self.lowest_n

        for i, (item_name, item) in enumerate(itemdict.items()):

            lbi = self.BuildLBI(item_name, item)

            lbi.Tag = item_name

            n_label = Label()
            n_label.Content = f"{lowest_n + i}"

            _logger.debug(f"{n_label=}")

            self.ItemNumbers.Children.Add(n_label)

            lbi.PreviewMouseLeftButtonDown += self.ReorderDlg_PrevMLBDown
            lbi.Drop += self.ReorderDlg_Drop
            lbi.DragOver += self.ReorderDlg_DragOver
            lbi.DragLeave += self.ReorderDlg_DragLeave
            lbi.QueryContinueDrag += self.ReorderDlg_QueryContinueDrag
            lbi.GiveFeedback += self.ReorderDlg_GiveFeedback

            _logger.debug(f"{lbi=}, {item_name=} {item=}")

            self.ItemListBox.Items.Add(lbi)

    def ReorderDlgPreviewMouseMove(self, caller, event):
        if event.LeftButton == MouseButtonState.Pressed:
            try:
                _logger.debug(f"{caller=} {event=}")
                _logger.debug(f"{event.LeftButton=}")
                pos_in_screen = event.GetPosition(None)
                ddx = pos_in_screen.X - self._dragstartpoint.X
                ddy = pos_in_screen.Y - self._dragstartpoint.Y

                source = event.OriginalSource
                while (source is not None and
                       not isinstance(source, ListBoxItem)):
                    if hasattr(source, 'VisualParent'):
                        source = source.VisualParent
                    elif hasattr(source, 'Parent'):
                        source = source.Parent

                if source is None:
                    _logger.debug(f"Bubbled from {event.OriginalSource=} and"
                                  " got to None before ListBoxItem")
                    return

                moved_enough = False

                if source != caller:
                    moved_enough = True

                moved_enough |= pow(pow(ddx, 2) + pow(ddy, 2), 0.5) >= 5

                pos_from_source = event.GetPosition(source)
                _logger.debug(f"X: {pos_from_source.X} Y:{pos_from_source.Y}"
                              f"{source.ActualHeight=} {source.ActualWidth=}")

                moved_enough |= (pos_from_source.X < 3 or
                                 pos_from_source.X > source.ActualWidth - 3 or
                                 pos_from_source.Y < 3 or
                                 pos_from_source.Y > source.ActualHeight - 3)

                if not moved_enough:
                    _logger.debug(f"drag more. {ddx=} {ddy=}")
                    return

                src_index = self.ItemListBox.Items.IndexOf(source)

                # _logger.debug(f"{source=} {src_index=}")

                if source is None:
                    return

                self.BuildPreviewWindow(source)
                source.Visibility = Visibility.Collapsed

                DragDrop.DoDragDrop(source, src_index, DragDropEffects.Move)
            except (AttributeError, ValueError) as e:
                _logger.error(f"Couldn't start drag: {e}")

    def BuildPreviewWindow(self, caller):
        _logger.debug(f"{caller=}")
        if self._dragdropwindow is not None:
            try:
                self._dragdropwindow.Close()
            except Exception as e:
                _logger.error(f"{e}")
            finally:
                self._dragdropwindow = None

        ddw = Window()
        self._dragdropwindow = ddw

        ddw.WindowStyle = getattr(WindowStyle, 'None')
        ddw.AllowTransparency = True
        ddw.AllowDrop = False
        ddw.Background = Brushes.White
        ddw.IsHitTestVisible = False
        ddw.SizeToContent = SizeToContent.WidthAndHeight
        ddw.Topmost = True
        ddw.ShowInTaskbar = False

        # r = self.CloneUsingXAML(caller)
        r = self.CloneUsingImage(caller)

        ddw.Content = r

        cursor_pos = GetCursorPos()

        ddw.Left = cursor_pos[0] + 10
        ddw.Top = cursor_pos[1] + 10
        ddw.Show()
        _logger.debug(f"{ddw=} {cursor_pos=}")

    @staticmethod
    def CloneUsingImage(uielement, dpi=96, width=None, height=None):
        bounds = VisualTreeHelper.GetDescendantBounds(uielement)
        rtb_scale = dpi / 96.0
        width = width if width else int((bounds.Width + bounds.X)
                                        * rtb_scale)
        height = height if height else int((bounds.Height + bounds.X)
                                           * rtb_scale)
        rtb_args = (int(width),
                    int(height),
                    dpi,
                    dpi,
                    PixelFormats.Pbgra32)
        renderTargetBitmap = RenderTargetBitmap(*rtb_args)

        dv = DrawingVisual()
        ctx = dv.RenderOpen()
        vb = VisualBrush(uielement)
        rect = Rect(bounds.X, bounds.Y, width/rtb_scale, height/rtb_scale)
        ctx.DrawRectangle(vb, None, rect)
        ctx.Close()
        renderTargetBitmap.Render(dv)

        # renderTargetBitmap.Render(uielement)

        img = Image()
        img.Width = width / rtb_scale
        img.Height = height / rtb_scale
        img.Source = renderTargetBitmap
        return img

    @staticmethod
    def CloneUsingXAML(uielement):
        r = Rectangle()
        r.Width = uielement.ActualWidth/2
        r.Height = uielement.ActualHeight/2

        clone = XamlReader.Load(XmlReader.Create(StringReader(
            XamlWriter.Save(uielement))))

        clone.IsSelected = False

        r.Fill = VisualBrush(clone)

        return r

    def ItemListBox_Drop(self, caller, event):
        src_index = event.Data.GetData(int)
        dest_index = len(self.ItemListBox.Items)

        _logger.debug(f"Dropped on List and not ListItem"
                      f"{src_index=} {dest_index=}")

        if src_index == dest_index or src_index < 0 or dest_index < 0:
            _logger.debug("Dropped on self, no change")
            return

        if src_index < dest_index:
            # Moving from above current position, we remove first so we
            # will end up moving the destination up.
            dest_index -= 1

        src_control = self.ItemListBox.Items[src_index]
        self.ItemListBox.Items.RemoveAt(src_index)
        self.ItemListBox.Items.Insert(dest_index, src_control)

    def ReorderDlg_DragOver(self, caller, event):
        event.Effects = getattr(DragDropEffects, 'None')
        src_index = event.Data.GetData(int)
        if src_index != self.ItemListBox.Items.IndexOf(caller):
            event.Effects = DragDropEffects.Move

            drop_pos = event.GetPosition(caller)
            # _logger.debug(f"{drop_pos.X=} {drop_pos.Y=} {caller.Height=}")

            if drop_pos.Y < caller.Height/2:
                # Top Half
                res_name = "TopHalf"
            else:
                res_name = "BottomHalf"

            caller.SetResourceReference(ListBoxItem.BackgroundProperty,
                                        res_name)

    def ReorderDlg_GiveFeedback(self, caller, event):
        # _logger.debug(f"{caller=} {event=}")
        cursor_pos = GetCursorPos()
        self._dragdropwindow.Left = cursor_pos[0] + 10
        self._dragdropwindow.Top = cursor_pos[1] + 10

    def ReorderDlg_DragLeave(self, caller, event):
        caller.ClearValue(ListBoxItem.BackgroundProperty)

    def ReorderDlg_Drop(self, caller, event):
        _logger.debug(f"{caller=} {event=}")

        if isinstance(caller, ListBoxItem):
            event.Handled = True  # Either way, this is the right destination
            caller.ClearValue(ListBoxItem.BackgroundProperty)
            src_index = event.Data.GetData(int)
            dest_index = self.ItemListBox.Items.IndexOf(caller)

            drop_pos = event.GetPosition(caller)

            if drop_pos.Y < caller.Height/2:
                # Top Half, insert "source" before "caller"
                pass
            else:
                # Insert "source" after "caller"
                dest_index += 1

            _logger.debug(f"{drop_pos.X=} {drop_pos.Y=} "
                          f"{src_index=} {dest_index=}")

            if src_index == dest_index or src_index < 0 or dest_index < 0:
                _logger.debug("Dropped on self, no change")
                return

            if src_index < dest_index:
                # Moving from above current position, we remove first so we
                # will end up moving the destination up.
                dest_index -= 1

            src_control = self.ItemListBox.Items[src_index]
            self.ItemListBox.Items.RemoveAt(src_index)
            self.ItemListBox.Items.Insert(dest_index, src_control)

    def ReorderDlg_PrevMLBDown(self, caller, event):
        self._dragstartpoint = event.GetPosition(None)

    def ReorderDlg_QueryContinueDrag(self, caller, event):
        # Reset the style of the drug beam name when the left mouse is
        # releaesed, do not mark as handled so normal handling finishes the
        # rest of the drop
        if not ((event.KeyStates & DragDropKeyStates.LeftMouseButton)
                == DragDropKeyStates.LeftMouseButton):
            _logger.debug(f"Stopping drag {event.KeyStates=}")
            # Left click released, this was a drop event.
            if isinstance(caller, ListBoxItem):
                caller.Visibility = Visibility.Visible

            if self._dragdropwindow is not None:
                self._dragdropwindow.Close()
                self._dragdropwindow = None

    def do_reorder(self):
        raise NotImplementedError(f"{self.__class__.__name__} must "
                                  "implement do_reorder")

    def OK_Click(self, caller, event):
        try:
            self.do_reorder()
            self.DialogResult = True
        finally:
            self.Close()


class BeamReorderDialog(GenericReorderDialog):
    _XAML = """
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        xmlns:d="http://schemas.microsoft.com/expression/blend/2008"
        xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
        xmlns:System="clr-namespace:System;assembly=mscorlib"
        Title="Select List"
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
        </Style>
        <Style TargetType="{x:Type Label}">
            <Setter Property="VerticalAlignment" Value="Center"/>
        </Style>
        <Style TargetType="{x:Type Button}">
            <Setter Property="Margin" Value="5" />
            <Setter Property="Padding" Value="5" />
        </Style>
        <Style TargetType="{x:Type ListBoxItem}">
            <Setter Property="Height" Value="42"/>
            <Setter Property="BorderBrush" Value="Black"/>
            <Setter Property="AllowDrop" Value="true"/>
            <Setter Property="HorizontalContentAlignment" Value="Stretch"/>
        </Style>
        <LinearGradientBrush x:Key="TopHalf" EndPoint="0.5,0.5"
                             StartPoint="0.5,0">
            <GradientStop Color="White" Offset="0"/>
            <GradientStop Color="#FF7C7C7C" Offset="0.05"/>
            <GradientStop Color="#FFF9F9F9" Offset="0.95"/>
            <GradientStop Color="White" Offset="1"/>
        </LinearGradientBrush>
        <LinearGradientBrush x:Key="BottomHalf" EndPoint="0.5,1"
                             StartPoint="0.5,0.5">
            <GradientStop Color="White" Offset="0"/>
            <GradientStop Color="#FFF9F9F9" Offset="0.05"/>
            <GradientStop Color="#FF7C7C7C" Offset="0.95"/>
            <GradientStop Color="White" Offset="1"/>
        </LinearGradientBrush>
        <SolidColorBrush x:Key="WhiteTransparent" Color="White"/>
    </Window.Resources>
    <Window.TaskbarItemInfo>
        <TaskbarItemInfo ProgressState="Normal" ProgressValue="50"/>
    </Window.TaskbarItemInfo>

    <StackPanel Background="#FFE6E6E6" MinHeight="20">
        <StackPanel Orientation="Horizontal" Margin="5">
            <Label x:Name="PickerLabel" Content="Beam Start Number:"/>
            <TextBox x:Name="FirstBeamNo" MinWidth="20">1</TextBox>
        </StackPanel>
        <StackPanel Orientation="Horizontal">
            <StackPanel x:Name="ItemNumbers">
                <Label>1</Label>
                <Label>2</Label>
            </StackPanel>
            <ListBox x:Name="ItemListBox" AllowDrop="True">
                <ListBoxItem Background="{DynamicResource TopHalf}"
                             Content="Beam_1 [10MV T0 G181-179]" />
                <ListBoxItem Background="{DynamicResource BottomHalf}"
                             Content="Beam_2 [10MV T0 G179-181]" />
                <ListBoxItem Background="{DynamicResource WhiteTransparent}"
                             Content="Beam_3 [10MV T0 G179-181]" />
            </ListBox>
        </StackPanel>
        <StackPanel Orientation="Horizontal" HorizontalAlignment="Center">
            <Button IsCancel="True" Content="_Cancel"/>
            <Button x:Name="BtnOK" IsDefault="True" Content="_OK" />
        </StackPanel>
    </StackPanel>
</Window>
"""

    FirstBeamNo = None  # Text

    def __init__(self, list_in, results):
        super().__init__(list_in, results)

        if 'description' in results:
            self.PickerLabel.Content = results['description']

        self.FirstBeamNo.Text = f"{self.lowest_n}"
        self.FirstBeamNo.TextChanged += self.FirstBeamChanged
        self.FirstBeamNo.PreviewMouseWheel += StaticMWHandler_IncDecScroll

        _logger.debug(f"{results=}")

    @staticmethod
    def BuildLBI(item_name, item):
        beam = item
        lbi = ListBoxItem()

        beam_desc = (f"{beam.BeamQualityId}MV "
                     f"T{beam.CouchRotationAngle:0.0f} "
                     f"G{beam.GantryAngle:0.0f}")

        if beam.ArcStopGantryAngle is not None:
            beam_desc += f"-{beam.ArcStopGantryAngle:0.0f}"

        dp = DockPanel()
        lbi.Content = dp
        dp.LastChildFill = False

        label = Label()
        label.Content = f"{item_name} [{beam_desc}]"
        dp.Children.Add(label)

        try:
            segment = beam.Segments[0]
            layer = beam.UpperLayer
            if layer.LeafCenterPositions is None or layer.LeafWidths is None:
                _logger.debug("Layer missing leaf positions\n"
                              f"{layer.LeafCenterPositions=}\n"
                              f"{layer.LeafWidths=}")
                machine = get_machine(beam)
                layer = machine.Physics.MlcPhysics.UpperLayer

            mlc_tb = MLCRenderTextBox(segment, layer)

            dp.Children.Add(mlc_tb)
            dp.SetDock(mlc_tb, Dock.Right)
        except ArgumentOutOfRangeException:
            pass

        gs = GantryRenderSlider(beam)
        dp.SetDock(gs, Dock.Right)
        dp.Children.Add(gs)

        try:
            """
            #  This is really slow, but still the fastest way.

            # Simplified to just using the initial jaw positions if they
            # exist, and if not the first CP.
            jaw_extremes = [(min(j), max(j)) for j in
                            zip(*[s.JawPositions for s in beam.Segments])]
            tt = (f"X1: {jaw_extremes[0][0]:0.1f}\n"
                    f"X2: {jaw_extremes[1][1]:0.1f}\n"
                    f"Y1: {jaw_extremes[2][0]:0.1f}\n"
                    f"Y2: {jaw_extremes[3][1]:0.1f}")
            """

            if beam.InitialJawPositions is not None:
                tt = (f"X1: {beam.InitialJawPositions[0]:0.1f}\n"
                      f"X2: {beam.InitialJawPositions[1]:0.1f}\n"
                      f"Y1: {beam.InitialJawPositions[2]:0.1f}\n"
                      f"Y2: {beam.InitialJawPositions[3]:0.1f}")
            else:
                tt = ("Segment 1 Jaw:\n"
                      f"X1: {beam.Segments[0].JawPositions[0]:0.1f}\n"
                      f"X2: {beam.Segments[0].JawPositions[1]:0.1f}\n"
                      f"Y1: {beam.Segments[0].JawPositions[2]:0.1f}\n"
                      f"Y2: {beam.Segments[0].JawPositions[3]:0.1f}")

            lbi.ToolTip = tt
        except (ValueError, TypeError, AttributeError,
                ArgumentOutOfRangeException):
            pass

        _logger.debug(f"{lbi=}, {item_name=}")
        return lbi

    @property
    def lowest_n(self):
        try:
            lowest_n = min([beam.Number for beam in self._list_in.values()])
        except (ValueError, AttributeError):
            lowest_n = 1
        return lowest_n

    def FirstBeamChanged(self, caller, event):
        # _logger.debug(f"{caller=} {event=}")
        try:
            newval = max(int(caller.Text), 1)
            caller.Text = f'{newval}'
            _logger.debug(f"{newval=}")
            for i, label in enumerate(self.ItemNumbers.Children):
                _logger.debug(f"{label=}, {label.Content=}")
                label.Content = f"{newval + i}"
        except (ValueError):
            _logger.error("Error with number")

    def do_reorder(self):
        beam_start = int(self.FirstBeamNo.Text)
        for i, item in enumerate(self.ItemListBox.Items):
            beam = self._list_in[item.Tag]
            # Add 100 to the number so we don't break things.
            beam.Number = 100 + beam_start + i
        for item in self.ItemListBox.Items:
            # Take the 100 back off, shouldn't have a collision
            self._list_in[item.Tag].Number -= 100


class SegmentReorderDialog(GenericReorderDialog):
    _XAML = """
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        xmlns:d="http://schemas.microsoft.com/expression/blend/2008"
        xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
        xmlns:System="clr-namespace:System;assembly=mscorlib"
        Title="Select List"
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
        </Style>
        <Style TargetType="{x:Type Label}">
            <Setter Property="VerticalAlignment" Value="Center"/>
        </Style>
        <Style TargetType="{x:Type Button}">
            <Setter Property="Margin" Value="5" />
            <Setter Property="Padding" Value="5" />
        </Style>
        <Style TargetType="{x:Type ListBoxItem}">
            <Setter Property="Height" Value="42"/>
            <Setter Property="BorderBrush" Value="Black"/>
            <Setter Property="AllowDrop" Value="true"/>
        </Style>
        <LinearGradientBrush x:Key="TopHalf" EndPoint="0.5,0.5"
                             StartPoint="0.5,0">
            <GradientStop Color="White" Offset="0"/>
            <GradientStop Color="#FF7C7C7C" Offset="0.05"/>
            <GradientStop Color="#FFF9F9F9" Offset="0.95"/>
            <GradientStop Color="White" Offset="1"/>
        </LinearGradientBrush>
        <LinearGradientBrush x:Key="BottomHalf" EndPoint="0.5,1"
                             StartPoint="0.5,0.5">
            <GradientStop Color="White" Offset="0"/>
            <GradientStop Color="#FFF9F9F9" Offset="0.05"/>
            <GradientStop Color="#FF7C7C7C" Offset="0.95"/>
            <GradientStop Color="White" Offset="1"/>
        </LinearGradientBrush>
        <SolidColorBrush x:Key="WhiteTransparent" Color="#7FFFFFFF"/>
        <System:Double x:Key="MLCRenderScale">1.0</System:Double>
    </Window.Resources>
    <Window.TaskbarItemInfo>
        <TaskbarItemInfo ProgressState="Normal" ProgressValue="50"/>
    </Window.TaskbarItemInfo>

    <StackPanel Background="#FFE6E6E6" MinHeight="20">
        <StackPanel Orientation="Horizontal" Margin="5">
            <Label x:Name="PickerLabel" Content="Beam Start Number:"/>
            <TextBox x:Name="FirstBeamNo" MinWidth="20">1</TextBox>
        </StackPanel>
        <StackPanel Orientation="Horizontal">
            <StackPanel x:Name="ItemNumbers">
                <Label>1</Label>
                <Label>2</Label>
            </StackPanel>
            <ListBox x:Name="ItemListBox" AllowDrop="True"
                     Tag="{DynamicResource MLCRenderScale}">
                <ListBox.Resources>
                    <Style TargetType="TextBox">
                        <Setter Property="FontSize" Value="{Binding Path=Tag,
                            RelativeSource={RelativeSource FindAncestor,
                            AncestorType={x:Type ListBox}}}"/>
                        <Setter Property="DockPanel.Dock" Value="Right"/>
                    </Style>
                    <Style TargetType="DockPanel">
                        <Setter Property="LastChildFill" Value="False"/>
                    </Style>
                </ListBox.Resources>
            </ListBox>
        </StackPanel>
        <StackPanel Orientation="Horizontal" HorizontalAlignment="Center">
            <Button IsCancel="True" Content="_Cancel"/>
            <Button x:Name="BtnOK" IsDefault="True" Content="_OK" />
        </StackPanel>
    </StackPanel>
</Window>
    """

    def __init__(self, list_in, results):
        self._beam = list_in

        segments = MakeMockery(self._beam, 'Segments')
        self.MLCRenderScale = self.calc_mlc_scale(segments)
        super().__init__(segments, results)

    @staticmethod
    def calc_mlc_scale(segments):
        MARGIN = 1
        HALF_WIDTH = 20.
        jaw_extreme = max(max(map(abs, j)) for j in
                          zip(*[s.JawPositions for s in segments]))

        # Scale to just beyond the largest jaw position (based on MARGIN)
        scale = HALF_WIDTH / (jaw_extreme + MARGIN)
        return scale

    def BuildLBI(self, item_name, item):
        segment = item
        layer = self._beam.UpperLayer
        if layer.LeafCenterPositions is None or layer.LeafWidths is None:
            _logger.debug("Layer missing leaf positions\n"
                          f"{layer.LeafCenterPositions=}\n"
                          f"{layer.LeafWidths=}")
            machine = get_machine(self._beam)
            layer = machine.Physics.MlcPhysics.UpperLayer

        lbi = ListBoxItem()

        dp = DockPanel()
        lbi.Content = dp
        dp.LastChildFill = False

        label = Label()
        label.Content = (f'Beam {obj_name(self._beam)}, '
                         f'CP{segment.SegmentNumber}')
        dp.Children.Add(label)

        mlc_tb = MLCRenderTextBox(segment, layer,
                                  scale=self.MLCRenderScale)

        dp.Children.Add(mlc_tb)

        return lbi

    def do_reorder(self):
        for i, (seg_out, item) in enumerate(zip(self._beam.Segments,
                                            self.ItemListBox.Items)):
            seg_in = self._list_in[item.Tag]
            seg_in.CopyTo(seg_out)


def renumber_beams(beamset, dialog=False):
    beam_map = {beam.Number: beam for beam in beamset.Beams}
    beam_nos = list(beam_map)
    non_sequential = any(map(lambda x, y: y != x+1,
                             beam_nos[:-1], beam_nos[1:]))

    # Map of beam names to original beam numbers

    if dialog:
        res = {}
        dlg = BeamReorderDialog(beamset.Beams, res)
        if dlg.ShowDialog():
            non_sequential = False

    if non_sequential:
        # Assume beams are ordered correctly, but some numbers were missed,
        # renumber from the first beam up.
        for i, beam in enumerate(beamset.Beams):
            beam.Number = beam_nos[0] + i

    _logger.debug(f"{beam_map=}")
    return {beam.Number: number for number, beam in beam_map.items()}


def obj_name(obj, name_identifier_object='.', strict=False):
    if isinstance(obj, str):
        return obj

    try:
        obj = rs_getattr(obj, name_identifier_object)
    except AttributeError:
        _logger.warning(f"{obj} has no attribute {name_identifier_object}")

    try:
        return rs_getattr(obj, [attr for attr in _NAMELIST if
                                rs_hasattr(obj, attr)][0])
    except IndexError:
        if strict:
            raise ValueError("No matching identifier")

        return str(obj)


def has_obj_name(obj, name_identifier_object='.'):
    try:
        obj = rs_getattr(obj, name_identifier_object)
    except AttributeError:
        _logger.warning(f"{obj} has no attribute {name_identifier_object}")

    return any(lambda attr: rs_hasattr(obj, attr), _NAMELIST)


def guess_name_id(obj_collection, first_guess=None):
    guess_list = []

    if first_guess:
        guess_list.append(first_guess)

    first_obj = next(iter(obj_collection))
    guess_list += [attr for attr in dir(first_obj) if attr[0:3] == 'For']

    for guess in guess_list:
        try:
            names = [obj_name(obj, guess, strict=True)
                     for obj in obj_collection]
            # Test for uniqueness
            if len(names) == len(set(names)):
                return guess
        except ValueError:
            continue

    raise ValueError("Unable to guess unique name id.")


def pick_list(obj_list, description="Select One", current=None, default=None):
    results = {'current': current,
               'default': default,
               'description': description}

    # Don't bother with a dialog if there is only one, or no choice(s).
    if len(obj_list) == 1:
        return next(iter(obj_list))
    elif len(obj_list) == 0:
        return None

    dlg = ListSelectorDialog(obj_list, results)
    try:
        res = dlg.ShowDialog()

        if not res:
            raise Warning("Closed with cancel")

    except Warning:
        _logger.warning("Dialog failed to run correctly.", exc_info=True)

    if 'Selected' in results:
        return results['Selected']
    else:
        return None


def pick_exam(exams=None, include_current=True, default=None,
              message="Select Exam:"):
    try:
        current = obj_name(get_current("Examination"))
    except InvalidDataException:
        _logger.debug("No current examination selected.")
        current = None

    exams = exams if exams else [exam for exam in
                                 get_current("Case").Examinations
                                 if include_current
                                 or obj_name(exam) != obj_name(current)]
    return pick_list(exams, message, current=current, default=default)


def pick_plan(plans=None, include_current=True, default=None,
              message="Select Plan:"):
    try:
        current = obj_name(get_current("Plan"))
    except InvalidDataException:
        _logger.debug("No current plan selected.")
        current = None

    plans = plans if plans else [plan for plan in
                                 get_current("Case").TreatmentPlans
                                 if include_current
                                 or obj_name(plan) != obj_name(current)]
    return pick_list(plans, message, current=current, default=default)


def pick_machine(current=None, default=None, match_on=None,
                 exclude_current=False, message="Select machine:"):
    def_filter_dict = {'IsLinac': True,
                       'HasMlc': True,
                       'Name': None,
                       'IsDynamicArcCapable': True,
                       'IsDynamicMlcCapable': True,
                       'IsStaticArcCapable': True,
                       'CommissionedBy': None,
                       'IsIonMachine': False,
                       'IsCyberKnifeLinac': False,
                       'HasRangeShifters': False,
                       'IsElectronCapable': None
                       }

    _logger.debug(f"{locals()}")
    if current is not None:
        current = {current} if isinstance(current, str) else set(current)
    else:
        current = {}

    if not match_on:
        match_on = [k for k in def_filter_dict
                    if def_filter_dict[k] is not None]

    machine_db = get_current("MachineDB")
    mach_query = machine_db.QueryCommissionedMachineInfo

    currentmachinfo = []
    for mach in current:
        currentmachinfo += mach_query(Filter={'Name': mach})

    currentmachinfo = (currentmachinfo + [def_filter_dict])[0]

    filter_dict = {k: currentmachinfo[k] for k in match_on}

    machines_info_list = mach_query(Filter=filter_dict)

    machines = [MachineQueryResult(**m) for m in machines_info_list]

    if exclude_current:
        for machine in machines:
            if machine.Name in current:
                machines.remove(machine)

    return pick_list(machines, message,
                     current=current, default=default)


@dataclass
class MachineQueryResult:
    Name: str
    NameAliases: str
    IsDeprecated: bool
    IsCommissioned: bool
    CommissionTime: object
    IsTemplate: bool
    IsDynamicArcCapable: bool
    IsDynamicMlcCapable: bool
    IsStaticArcCapable: bool
    CommissionedBy: str
    HasMlc: bool
    IsLinac: bool
    IsIonMachine: bool
    IsCyberKnifeLinac: bool
    HasRangeShifters: bool
    IsElectronCapable: bool
    SupportsOcularGaze: bool
    PatientSupportType: str
    IsRbeIncluded: bool = False

    @property
    def Alias(self):
        return self.NameAliases


class Machine(IndirectInheritanceClass):
    _energies = None

    def __init__(self, machine):
        if self.PhotonBeamQualities is None:
            raise NotImplementedError("Only support for photons machines.")

    @property
    def photon_energies(self):
        if not self._energies:
            # Sort by increasing nominal energy, this will let us pull the
            # nearest value not above the current energy
            energies = sorted(self.PhotonBeamQualities,
                              key=lambda e: e.NominalEnergy)
            self._energies = {(f'{int(e.NominalEnergy)}'
                               if e.FluenceMode is None else
                               f'{int(e.NominalEnergy)} {e.FluenceMode}'): e
                              for e in energies}
        return self._energies

    def closest_energy(self, energy):
        energies = self.photon_energies
        if energy in energies:
            return energy

        nominal_energy = int(energy.rstrip(" FFF"))
        isfff = 'FFF' in energy

        if isfff:
            if f'{nominal_energy}' in energies:
                return f'{nominal_energy}'
        else:
            fff_energy = f'{energy} FFF'
            if fff_energy in energies:
                return fff_energy

        try:
            return [e for e in energies if isfff == ('FFF' in e)][0]
        except IndexError:
            return next(iter(energies))

    def get_beam_presentation_vals(self, beam):
        """
        Translates beam Iec61217 standard values into the presentation format
        specified in the beam commissioning for each collimating component.

        beam: Object presenting beam parameters

        returns: Dict containing values.
        """
        retdict = {'Gantry': None,
                   'GantryStop': None,
                   'Collimator': None,
                   'Couch': None}

        # Gantry
        if self.GantryScale == 'Iec61217':
            retdict['Gantry'] = beam.GantryAngle
            retdict['GantryStop'] = beam.ArcStopGantryAngle
        elif self.GantryScale == 'VarianStandard':
            retdict['Gantry'] = (-beam.GantryAngle + 180) % 360
            retdict['GantryStop'] = (-beam.ArcStopGantryAngle + 180) % 360
        else:
            raise NotImplementedError(
                f"Unsupported Scale '{self.GantryScale}'")

        # Collimator
        try:
            collimator = beam.Segments[0].CollimatorAngle
        except ArgumentOutOfRangeException:
            collimator = beam.InitialCollimatorAngle

        if self.CollimatorScale == 'Iec61217':
            retdict['Collimator'] = collimator
        elif self.CollimatorScale == 'VarianStandard':
            retdict['Collimator'] = (-collimator + 180) % 360
        else:
            raise NotImplementedError(
                f"Unsupported Scale '{self.CollimatorScale}'")

        # Couch
        if self.CouchScale == 'Iec61217':
            retdict['Couch'] = beam.CouchRotationAngle
        elif self.CouchScale == 'VarianIec':
            retdict['Couch'] = (-beam.CouchRotationAngle) % 360
        elif self.CouchScale == 'VarianStandard':
            retdict['Couch'] = (-beam.CouchRotationAngle + 180) % 360
        else:
            raise NotImplementedError(
                f"Unsupported Scale '{self.CouchScale}'")

        return retdict


def get_machine(machine_ref):
    try:
        machine_name = f'{machine_ref.MachineReference.MachineName}'
    except AttributeError:
        machine_name = f'{machine_ref}'

    if machine_name not in _INDIRECT_MACHINE_REF:
        mach_db = get_current("MachineDB")
        mach = Machine(mach_db.GetTreatmentMachine(machineName=machine_name))
        _INDIRECT_MACHINE_REF[machine_name] = mach

    return _INDIRECT_MACHINE_REF[machine_name]


def pick_site(sites=None, current=None, default=None):
    if sites is None:
        site_settings = get_current("ClinicDB").GetSiteSettings()
        site_defs = site_settings.DefaultSettings.BodySiteDefinitions
        sites = [obj_name(site) for site in site_defs]

    return pick_list(sites, "Select site:", current=current, default=default)


def dup_object_param_values(obj_in, obj_out,
                            includes=None, excludes=[], sub_objs=[], _depth=0):
    if obj_in is None:
        raise TypeError("Got passed a nonetype object to copy from.")

    if _depth > __opts['DUP_MAX_RECURSE']:
        raise RecursionError(f"{__name__} too deep ({_depth} layers),"
                             " this may be a self referential object.")

    sub_obj_depth = max([s.count('.') for s in sub_objs] + [0])
    if sub_obj_depth > __opts['DUP_MAX_RECURSE']:
        raise ValueError(f"Subobjects too deep ({sub_obj_depth} > "
                         f"{__opts['DUP_MAX_RECURSE']}): {sub_objs=}")

    # TODO: Consider exclududing any objects which are PyScriptObjects unless
    # explicitly included.

    # Get the list of sub_objects we might be acting on.
    sub_o_set = {sub_o for sub_o in sub_objs
                 if (rs_hasattr(obj_out, sub_o)
                     and rs_getattr(obj_out, sub_o) is not None)}

    # Objects to act on directly, copying everything in them.
    sub_o_root_set = {sub_o for sub_o in sub_o_set if '.' not in sub_o}

    # Objects who have a deep component to be acted on later in the recursed
    # dup_obj_param_values call.
    sub_o_deep_set = {sub_o for sub_o in sub_o_set if '.' in sub_o}
    sub_o_deep_root_set = {sub_o.split('.', 1)[0] for sub_o in sub_o_deep_set}

    # All roots, including shallow, shallow+deep, and deep only
    sub_o_all_root_set = sub_o_root_set | sub_o_deep_root_set

    # Mapping of sub_objs to pass to later dup_obj_param_values calls.
    sub_o_deep_set_map = {o_root: {sub_sub_o.split('.', 1)[1] for sub_sub_o
                                   in sub_o_deep_set
                                   if sub_sub_o.split('.', 1)[0] == o_root}
                          for o_root in sub_o_all_root_set}

    # Objects with deep sets but no root set to copy (Handle differently from
    # the normal objects
    sub_o_deep_only_root_set = sub_o_deep_root_set - sub_o_root_set

    # If passed a sub object with its own sub objects, assume that we cannot
    # use it in the list of params to be copied alone.
    top_excludes = sub_o_root_set | sub_o_deep_root_set | set(excludes)

    if includes is None:
        top_includes = set(dir(obj_out))
    else:
        top_includes = {inc for inc in includes if '.' not in inc}

    # Any objects in top that are callble should be excluded
    top_callables = {p for p in top_includes if rs_callable(obj_out, p)}

    # Any objects in top that are Script Collections or ScriptObjects should be
    # excluded.
    top_scriptitems = {p for p in top_includes
                       if 'Script' in (type(rs_getattr(obj_out, p))).__name__}

    valid_top_params = (top_includes - top_callables) - top_scriptitems

    params = valid_top_params - top_excludes
    for param in params:
        value = rs_getattr(obj_in, param)
        try:
            setattr(obj_out, param, value)
            _logger.debug(f'{"":->{_depth}s}{"":>>{_depth>0:d}s}'
                          f'Set {param}={value} on {obj_out}')
        except InvalidOperationException:
            _logger.debug(f'{"":->{_depth}s}{"":>>{_depth>0:d}s}'
                          f'Failed to set {param}={value} on {obj_out}')

    # Loop through objects to be copied
    for sub_obj in sub_o_root_set:
        sub_in = rs_getattr(obj_in, sub_obj)
        sub_out = rs_getattr(obj_out, sub_obj)

        # Explicitly requested objects to copy.
        sub_sub_objs = sub_o_deep_set_map[sub_obj]  # This may be an empty set

        # Exclude anything already excluded in the dot notation
        sub_excludes = {exc.split('.', 1)[1] for exc in excludes
                        if '.' in exc and sub_obj == exc.split('.', 1)[0]}

        sub_includes = None
        if includes:
            sub_includes = {inc.split('.', 1)[1] for inc in includes
                            if '.' in inc and inc.split('.', 1)[0] == sub_obj}

        if not sub_includes and sub_obj not in sub_o_deep_only_root_set:
            sub_includes = None

        # Add excludes for all objects in root that are not in the sub_sub_objs
        # list if this is a member of the sub_o_deep_only_root_set.
        dup_object_param_values(sub_in,
                                sub_out,
                                includes=sub_includes,
                                excludes=sub_excludes,
                                sub_objs=sub_sub_objs,
                                _depth=_depth+1)
    return None


class CallLaterList():
    _fn_list = {}  # Class level list

    def _def_fn(self, *args, **kwargs):
        raise NotImplementedError("Must be initialised first.")

    def __getattr__(self, fn):
        if fn not in self._fn_list:
            self._fn_list[fn] = CallLater()
        return self._fn_list[fn]

    def __call__(self, fn):
        fnname = fn.__name__
        myfn = self.__getattr__(fnname)
        myfn.set_fn(fn)
        return myfn


class CallLater():
    _myfn = None

    def __call__(self, *args, **kwargs):
        return self._myfn(*args, **kwargs)

    def set_fn(self, fn):
        self._myfn = fn


def get_unique_name(obj, container, char_limit=64):
    if isinstance(container, set):
        limiting_set = container
    elif rs_hasattr(container, 'Keys'):
        limiting_set = set(container.Keys)
    else:
        try:
            limiting_set = set(map(obj_name, container))
        except (ValueError, AttributeError):
            limiting_set = set(container)

    o_name = obj_name(obj)
    oo_name = o_name
    n = 1
    while o_name in limiting_set:
        o_name = f'{oo_name[0:(char_limit - 5 - n//10)]} ({n})'
        n += 1

    return o_name


class ObjectDict(dict):
    _name_id = None

    def __init__(self, obj_collection=None, name_identifier='.'):
        super().__init__()

        self._name_id = guess_name_id(obj_collection, name_identifier)

        if obj_collection is not None:
            self.update(obj_collection)

    def update(self, collection):
        if type(collection).__name__ == 'PyScriptObjectCollection':
            return super().update({obj_name(obj, self._name_id): obj
                                   for obj in collection})
        else:
            return super().update(collection)

    def __and__(self, other):
        return self.keys() & other.keys()


def params_from_mapping(obj, param_map, default_map=None):
    if default_map:
        params = deepcopy(default_map)
    else:
        params = {}

    map_p = {key: (param_map[key](obj) if callable(param_map[key])
                   else (rs_getattr(obj, key) if rs_hasattr(obj, key) else
                         rs_getattr(obj, param_map[key])))
             for key in param_map
             if key and (callable(param_map[key])
                         or rs_hasattr(obj, param_map[key])
                         or rs_hasattr(obj, key))}

    params.update(map_p)
    return params


class LimitedDict(MutableMapping):
    """A dictionary that limits the keys returned for iteration to those
    present in the _keylist attribute.  If the dictionary is initialized with
    key: value pairs, those _keylist is initialized to those keys."""
    _keylist: Type[set] = None
    store: Type[dict]

    def __init__(self, *args, **kwargs):
        if len(args) == 1 and args[0] is None:
            self.store = dict(**kwargs)
        else:
            self.store = dict(*args, **kwargs)

        if self.store:
            self._keylist = set(self.store)

    def keys(self):
        keylist = self.store.keys()
        return keylist & self._keylist if self._keylist else keylist

    @property
    def limiter(self):
        return set(self._keylist) if self._keylist else None

    @limiter.setter
    def limiter(self, limiter):
        self._keylist = set(limiter)

    def __getitem__(self, key):
        return self.store[key]

    def __setitem__(self, key, value):
        self.store[key] = value

    def __delitem__(self, key):
        del self.store[key]

    def __iter__(self):
        return iter(self.keys())

    def __len__(self):
        return len(self.store)

    @property
    def __class__(self):
        return dict

    def update(self, *args, **kwargs):
        if len(args) == 1 and args[0] is None:
            return
        super().update(*args, **kwargs)


def clamp(lower, val, upper):
    return val if lower <= val <= upper else upper if val > upper else lower


def sequential_dedup_return_list(func):
    """Decorator function to remove sequentially duplicate items in a list
    that was returned from the passed function """

    def f_out(*args, **kwargs):
        inlist = func(*args, **kwargs)
        outlist = []
        try:
            last = None
            for item in inlist:
                if item != last:
                    outlist.append(item)
                last = item

            return outlist
        except (TypeError, IndexError, ValueError):
            return inlist

    return f_out


# __all__ = [dcmread, CompositeAction, get_current]
