
import sys
import re

from System.Windows.Input import Keyboard, ModifierKeys
from System.Windows.Controls import CheckBox
from System import InvalidOperationException

from .external import (RayWindow, CompositeAction, get_current, set_progress,
                       Show_YesNo, Show_OK)

from copy import copy

import logging

logger = logging.getLogger(__name__)

CONFLICT_RE = re.compile(r'Conflicting dose levels in (.*) \([^)]*\)\.')

DEFAULT_OPTS = {'iterations': 240,
                'cycles': 6,
                'dvhscaling': []}

BEAM_OPT_SETTINGS = {'OptimizationTypes': ['SegmentOpt', 'SegmentMU'],
                     'SelectCollimatorAngle': False,
                     'AllowBeamSplit': False,
                     'JawMotion': "Use limits as max",
                     'LeftJaw': -20,
                     'RightJaw': 20,
                     'TopJaw': 18,
                     'BottomJaw': -18}

ARC_OPT_SETTINGS = {'CreateDualArcs': False,
                    'FinalGantrySpacing': 2,
                    'MaxArcDeliveryTime': 60,
                    'BurstGantrySpacing': None,
                    'MaxArcMU': None}

DYN_JAW_SHIELD = 2

LIMITING_MAX_FNTYPES = ('MaxDose', 'UniformDose', 'MaxDVH')

# Minimum number of iterations per cycle for reasonableness, used to define the
# number of "Preparatory" iterations for cycles as well.
MINIPERCYCLE = 15

__OPT_XAML = """
<Window
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
    xmlns:System="clr-namespace:System;assembly=mscorlib"
    Title="Optimizer Sequecing" SizeToContent="WidthAndHeight"
    ResizeMode="NoResize">
    <StackPanel>
        <StackPanel.Resources>
            <Style TargetType="{x:Type DockPanel}">
                <Setter Property="Margin" Value="10,5"/>
            </Style>
            <Style TargetType="{x:Type StackPanel}">
                <Setter Property="Margin" Value="10,5"/>
            </Style>
        </StackPanel.Resources>
        <StackPanel Orientation="Horizontal">
            <Button x:Name="A1Binding" Content="_1" Width="0" Height="0"
                Focusable="False"/>
            <Button x:Name="A3Binding" Content="_3" Width="0" Height="0"
                Focusable="False"/>
            <Label Content="Iterations per Cycle"
                HorizontalAlignment="Left" VerticalAlignment="Center"/>
            <TextBox x:Name="cIterations" MinWidth="24"
                TextChanged="cIterations_TextChanged"
                PreviewMouseWheel="PreviewMouseWheelHandler"
                TextAlignment="Center" IsUndoEnabled="False" MaxLines="1"
                VerticalContentAlignment="Center"
                HorizontalContentAlignment="Center"/>
            <Label Content="Total Iterations:"/>
            <TextBox x:Name="cTotalIterations" MinWidth="24"
                TextAlignment="Center" IsUndoEnabled="False" MaxLines="1"
                VerticalContentAlignment="Center"
                HorizontalContentAlignment="Center"
                IsEnabled="False"/>
        </StackPanel>
        <DockPanel>
            <Label Content="Number of Cycles" HorizontalAlignment="Left"
                VerticalAlignment="Center"/>
            <TextBox x:Name="cCyclesTB" HorizontalAlignment="Left"
                MinWidth="24" DockPanel.Dock="Right"/>
            <Slider x:Name="cCyclesSL" VerticalAlignment="Center"
                MinWidth="129" Minimum="1" SmallChange="1"
                TickPlacement="BottomRight" Maximum="20"
                PreviewMouseWheel="PreviewMouseWheelHandler"/>
        </DockPanel>
        <StackPanel Orientation="Horizontal">
            <CheckBox x:Name="ScaleMinDVH" Content="_Scale MinDVH functions?"
                VerticalAlignment="Top"
                AutomationProperties.HelpText="Select this to scale MinDVH \
                    functions by the amount they are failing to meet the goal"
                IsChecked="True"/>
            <StackPanel x:Name="Scaled_Functions" VerticalAlignment="Center"
                MinHeight="19" HorizontalAlignment="Left"
                IsEnabled="{Binding IsChecked, ElementName=ScaleMinDVH}"
                Margin="10,0">
                <CheckBox Content="DVH Function"/>
            </StackPanel>
        </StackPanel>
        <StackPanel Orientation="Horizontal" VerticalAlignment="Center"
                HorizontalAlignment="Center" >
            <Button x:Name="Launch" Content="Launch" Click="Launch_Click"
                Margin="10,0" MinWidth="75" IsDefault="True"/>
            <Button x:Name="Cancel" Content="Cancel" IsCancel="True"
                Margin="10,0" MinWidth="75"/>
        </StackPanel>
    </StackPanel>
</Window>
"""

ModifierKeys_None = 0

ValScale = {ModifierKeys_None: 1,
            ModifierKeys.Control: 5,
            ModifierKeys.Shift: 10,
            ModifierKeys.Control | ModifierKeys.Shift: 50}


def dosefn_str(optfn):
    dfp = optfn.DoseFunctionParameters
    try:
        if dfp.FunctionType == 'MinDvh':
            fmts = [optfn.ForRegionOfInterest.Name, dfp.PercentVolume,
                    dfp.DoseLevel, dfp.Weight]
            return '{} D{:.0f}%<={} cGy (w: {})'.format(*fmts)
    except AttributeError:
        return '{}'.format(optfn.ForRegionOfInterest.Name)


class ObjectiveError(ValueError):
    # Custom error to indicate that optimization failed due to a dose objective
    # conflict.
    pass


class MinDVHFunctionsControl():
    _isSelected = True
    _dvhtext = ""
    _dvh_fn = None

    def __init__(self, dvhfunction=None):
        logger.debug("{}".format(str(self.__class__)))
        if dvhfunction:
            try:
                self.IsSelected = True
                self.DVHText = dosefn_str(dvhfunction)
                self._dvh_fn = dvhfunction
            except AttributeError:
                pass

    def OnPropertyChanged(self, prop):
        logger.debug("Changed {} in {}".format(str(prop), str(self)))

    @property
    def IsSelected(self):
        return self._isSelected

    @IsSelected.setter
    def IsSelected(self, value):
        self._isSelected = bool(value)
        self.OnPropertyChanged("IsSelected")

    @property
    def DVHText(self):
        return self._dvhtext

    @DVHText.setter
    def DVHText(self, value):
        self._dvhtext = str(value)
        self.OnPropertyChanged("DVHText")


class BulkOptDialogWindow(RayWindow):
    outdict = None
    dvhfuncs = None

    def __init__(self, outdict, optimizer):
        self.LoadComponent(__OPT_XAML)

        self.outdict = outdict

        for opt in DEFAULT_OPTS:
            if opt not in self.outdict:
                self.outdict[opt] = copy(DEFAULT_OPTS[opt])

        self.cCyclesTB.Text = '%d' % self.outdict['cycles']
        self.cCyclesTB.TextChanged += self.cCyclesTB_TextChanged
        self.cCyclesTB.PreviewMouseWheel += self.PreviewMouseWheelHandler

        self.cIterations.Text = '%d' % int(self.outdict['iterations'] /
                                           self.outdict['cycles'])
        self.optimizer = optimizer

        self.dvhfuncs = {}

        self.Scaled_Functions.Children.Clear()

        self.cCyclesSL.ValueChanged += self.cCyclesSL_ValueChanged
        self.cCyclesSL.Value = self.outdict['cycles']

        self.A1Binding.Click += self.singleiteration
        self.A3Binding.Click += self.threeiterations

        for optfn in self.optimizer.Objective.ConstituentFunctions:
            if (hasattr(optfn, 'DoseFunctionParameters') and
                    hasattr(optfn.DoseFunctionParameters, 'FunctionType') and
                    optfn.DoseFunctionParameters.FunctionType == 'MinDvh'):
                self.addbox(optfn)

    def singleiteration(self, sender, e):
        self.cCyclesSL.Value = 1

    def threeiterations(self, sender, e):
        self.cCyclesSL.Value = 3

    def addbox(self, boxtext):
        scalefns = self.Scaled_Functions
        newbox = MinDVHFunctionsControl(boxtext)
        row = scalefns.Children.Count

        cb = CheckBox()
        cb.Content = newbox.DVHText
        cb.IsChecked = newbox.IsSelected
        scalefns.Children.Add(cb)
        self.dvhfuncs[row] = newbox

    def getselectedopts(self):
        outfns = []
        if self.ScaleMinDVH.IsChecked:
            for row, checkbox in enumerate(self.Scaled_Functions.Children):
                if row in self.dvhfuncs and checkbox.IsChecked:
                    outfns.append(self.dvhfuncs[row]._dvh_fn)
        return outfns

    def Launch_Click(self, sender, e):
        try:
            iterations = int(self.cTotalIterations.Text)
        except ValueError:
            iterations = DEFAULT_OPTS['iterations']

        cycles = int(self.cCyclesSL.Value)
        self.outdict['cycles'] = cycles
        self.outdict['iterations'] = iterations

        self.outdict['dvhscaling'] = self.getselectedopts()

        self.DialogResult = True

    def cCyclesTB_TextChanged(self, sender, e):
        logger.debug("Got text changed from {!s}".format(sender))
        try:
            value = max(int(sender.Text), 1)
        except ValueError as exc:
            m = "Couldn't get int from value given text {}".format(sender.Text)
            logger.debug(m)
            logger.exception(exc)
            value = DEFAULT_OPTS['cycles']

        if sender.Text != '%d' % value and sender.Text != '':
            sender.Text = '%d' % value

        if self.cCyclesSL.Value != value:
            self.cCyclesSL.Value = value

        self.outdict['cycles'] = value

        self.validate_ti()

    def cIterations_TextChanged(self, sender, e):
        try:
            value = max(int(sender.Text), MINIPERCYCLE)
        except ValueError as exc:
            m = "Couldn't get int from value given text {}".format(sender.Text)
            logger.debug(m)
            logger.exception(exc)
            value = int(DEFAULT_OPTS['iterations'] / self.outdict['cycles'])

        if sender.Text != '%d' % value and sender.Text != '':
            sender.Text = '%d' % value

        self.validate_ti()

    def cCyclesSL_ValueChanged(self, sender, e):
        value = int(sender.Value)
        self.cCyclesTB.Text = '%d' % value

        self.validate_ti()

    def PreviewMouseWheelHandler(self, sender, e):
        try:
            scale = ValScale.get(Keyboard.Modifiers, 1)
            valdelta = int(e.Delta * scale / 120.)

            if hasattr(sender, "Value"):
                sender.Value += valdelta
            elif hasattr(sender, "Text"):
                sender.Text = '%d' % (int(sender.Text) + valdelta)

        except ValueError:
            pass
        except Exception as ex:
            logger.exception(ex)

    def validate_ti(self):
        value = int(self.cIterations.Text) * int(self.cCyclesTB.Text)

        self.cTotalIterations.Text = '%d' % value


class BulkOptimizer():
    options = None
    optimizer = None
    __default_opts__ = DEFAULT_OPTS

    def __init__(self, plan, beam_set, **kwargs):

        self.options = copy(self.__default_opts__)
        for optfn in self.optimizer.Objective.ConstituentFunctions:
            try:
                if optfn.DoseFunctionParameters.FunctionType == 'MinDvh':
                    self.options['dvhscaling'].append(optfn)
            except AttributeError:
                pass

        for key in kwargs:
            if key in self.options and kwargs[key] is not None:
                self.options[key] = kwargs[key]

        self.optimizer = get_beamset_opt(plan, beam_set)

        if self.optimizer is None:
            raise SystemError("No optimization found for beamset {}".format(
                beam_set.DicomPlanLabel))

        self.mindvhlimiters = get_mindvhlimiters(self.optimizer)

    def show_options_dialog(self):
        window = BulkOptDialogWindow(outdict=self.options,
                                     optimizer=self.optimizer)
        if not window.ShowDialog():
            logger.warning("Dialog Cancelled.")
            return False
        else:
            return True

    def run(self):
        return runbulkopt(self.options, self.mindvhlimiters, self.optimizer)


def buildoptsettings(beamsetting):
    opt_settings = BEAM_OPT_SETTINGS.copy()
    arc_opt_settings = ARC_OPT_SETTINGS.copy()

    beam = beamsetting.ForBeam

    machinename = beam.MachineReference.MachineName
    mach_db = get_current("MachineDB")
    machine = mach_db.GetTreatmentMachine(machineName=machinename)

    yjawlimit = machine.Physics.JawPhysics.MaxBottomJawPos - DYN_JAW_SHIELD
    xjawlimit = machine.Physics.JawPhysics.MaxRightJawPos
    max_speed = machine.ArcProperties.MaxGantryAngleSpeed

    if beam.InitialJawPositions is not None:
        opt_settings['LeftJaw'] = beam.InitialJawPositions[0]
        opt_settings['RightJaw'] = beam.InitialJawPositions[1]
        opt_settings['TopJaw'] = max(beam.InitialJawPositions[2], -yjawlimit)
        opt_settings['BottomJaw'] = min(beam.InitialJawPositions[3], yjawlimit)
    else:
        opt_settings['LeftJaw'] = -xjawlimit
        opt_settings['RightJaw'] = xjawlimit
        opt_settings['TopJaw'] = -yjawlimit
        opt_settings['BottomJaw'] = yjawlimit

    opt_settings['AllowBeamSplit'] = beamsetting.AllowBeamSplit

    if beam.DeliveryTechnique == 'DynamicArc':
        a_start = beam.GantryAngle
        a_stop = beam.ArcStopGantryAngle

        arc_len = abs(((a_start + 180) % 360) - ((a_stop + 180) % 360))

        arc_opt_settings['MaxArcDeliveryTime'] = arc_len / max_speed
    else:
        arc_opt_settings = None

    return opt_settings, arc_opt_settings


def update_machine_limits(current_opt):
    # Set machine limits for all beams in current set.

    for tx_setup in current_opt.OptimizationParameters.TreatmentSetupSettings:
        for beamsetting in tx_setup.BeamSettings:
            opt_settings, arc_opt_settings = buildoptsettings(beamsetting)

            logger.debug(f'{opt_settings=}')
            logger.debug(f'{arc_opt_settings=}')
            logger.debug(f'{beamsetting=}')

            # Needed because RS throws an exception when it doesn't make any
            # changes.
            beamsetting.OptimizationTypes = []
            beamsetting.EditBeamOptimizationSettings(**opt_settings)

            acppb = beamsetting.ArcConversionPropertiesPerBeam

            if arc_opt_settings:
                gs = arc_opt_settings['FinalGantrySpacing']
                adt = arc_opt_settings['MaxArcDeliveryTime']
                acppb.FinalArcGantrySpacing = gs

                # Only modify  MaxArcDeliveryTime if it hasn't been set already
                # (default is 90)
                if acppb.MaxArcDeliveryTime == 90:
                    acppb.MaxArcDeliveryTime = adt

                # Causes an exception when there are no changes
                # acppb.EditArcBasedBeamOptimizationSettings(**arc_opt_settings)


def runbulkopt(options, mindvhlimiters, current_opt):
    cycleiters = int(options['iterations'] / options['cycles'])
    actname = (f"Bulk Optimization "
               f"({cycleiters:d} iterations x {options['cycles']:d} runs)")

    # Only run on first beam_set in opt. TODO: work with multibeamset opts.
    beam_set = current_opt.OptimizedBeamSets[0]
    with CompositeAction(actname):

        update_machine_limits(current_opt)

        beam_set.SetAutoScaleToPrimaryPrescription(AutoScale=False)

        scaledoses = [(optfn.ForRegionOfInterest.Name,
                       float(optfn.DoseFunctionParameters.DoseLevel),
                       optfn) for optfn in options['dvhscaling']]

        logger.debug(f'{scaledoses=}')

        op = current_opt.OptimizationParameters
        op.Algorithm.MaxNumberOfIterations = cycleiters
        op.DoseCalculation.IterationsInPreparationsPhase = MINIPERCYCLE

        set_progress(message=actname, percentage=0)
        progmsg = "Optimizing {} of {}"
        for i in range(options['cycles']):
            set_progress(message=progmsg.format(i+1, options['cycles']),
                         percentage=(100.*(i+1)/(options['cycles'])))
            try:
                current_opt.RunOptimization()
            except InvalidOperationException as e:
                # Optimizer failed for some reason.  All exceptions come from
                # RayStation in the form of AggregateErrors, so we have to
                # parse the message to find the proximate cause.
                if hasattr(e, 'Message'):
                    if 'Cannot compute' in e.Message:
                        # Failed to calculate, try to report the reason to the
                        # user and abort optimization.
                        if 'not been commissioned' in e.Message:
                            msg = "Machine is not commissioned for use."
                        else:
                            msg = "Unknown error optimizing."
                        msg += "\nSee log for more details."
                        raise Warning("Failed to optimize", msg)
                    elif CONFLICT_RE.search(e.Message):
                        # One or more of the doses we are scaling cannot be
                        # scaled due to a Uniform Dose or Max Dose constraint.
                        # We will try just removing the ROI from the options
                        # list and throwing a warning.  We can potentially
                        # rerun the optimization with this objective removed if
                        # the user agrees.
                        #
                        # NOTE: If we try to run again while inside of a
                        # CompositeAction after RayStation throws an error and
                        # before allowing the composite action to complete, we
                        # will get a fatal error in RS, so we have to drop back
                        # out of the "with CompositeAction():" before trying
                        # again.
                        roi_conflicts = set(CONFLICT_RE.findall(e.Message))
                        removefailedobjectives(options, roi_conflicts)
                        msg = f'Failed due to roi conflicts: {roi_conflicts}'
                        raise ObjectiveError("Failed to optimize", msg)
                    else:
                        try:
                            base_e = e.GetBaseException()
                            logger.error(f"{base_e}", exc_info=True)
                        except AttributeError:
                            pass

                        raise e
                else:
                    logger.info(f'Failed with InvalidOperationException: {e}')
                    raise e
            scaleobjectives(beam_set, scaledoses, mindvhlimiters)
            i += 1

        # Restore dose levels to pre-optmization value (prevent re-opt
        # creep)
        # TODO: might want to consider storing last opt numbers as well
        for roi, origDoseLevel, optfn in scaledoses:
            optfn.DoseFunctionParameters.DoseLevel = origDoseLevel


def removefailedobjectives(options, roi_conflicts):
    newoptfns = [optfn for optfn in options['dvhscaling']
                 if optfn.ForRegionOfInterest.Name not in roi_conflicts]

    options['dvhscaling'] = newoptfns

    logger.warning(f'Removed rois "{roi_conflicts}" from'
                   ' scaling due to conflicting goals.')


def scaleobjectives(beam_set, scaledoses, mindvhlimiters):
    # Parse if the optimization needs to be rescaled per target.
    for roi, origDoseLevel, optfn in scaledoses:
        gdarv = beam_set.FractionDose.GetDoseAtRelativeVolumes
        pv = optfn.DoseFunctionParameters.PercentVolume
        nfx = beam_set.FractionationPattern.NumberOfFractions
        dl = optfn.DoseFunctionParameters.DoseLevel
        doseatvol = gdarv(RoiName=roi,
                          RelativeVolumes=[pv / 100.])[0] * nfx
        newdose = dl + origDoseLevel - doseatvol
        if roi in mindvhlimiters and newdose > mindvhlimiters[roi]:
            newdose = mindvhlimiters[roi]
            logger.warning(f'Clamped MinDVH for {roi} to {newdose}.'
                           ' Investigate if the dose levels need to be'
                           ' adjusted for limits.')

        optfn.DoseFunctionParameters.DoseLevel = newdose
        logger.debug(f'Scaled {roi} MinDVH from {dl} to {newdose}')


def get_beamset_opt(plan, beam_set):
    for opt in plan.PlanOptimizations:
        if beam_set in opt.OptimizedBeamSets:
            return opt

    return None


def get_mindvhlimiters(optimizer):
    constfns = optimizer.Objective.ConstituentFunctions
    roilimits = {}
    for fn in constfns:
        roi = fn.ForRegionOfInterest.Name
        dfp = fn.DoseFunctionParameters
        try:
            if dfp.FunctionType in LIMITING_MAX_FNTYPES:
                # New limit is the lesser of the existing limit or the
                # doselevel here.  If we don't have a current limit, default to
                # the current doselevel here.
                roilimits[roi] = min(dfp.DoseLevel,
                                     roilimits.get(roi, dfp.DoseLevel))
        except (SystemError, AttributeError) as e:
            logger.debug(str(e), exc_info=True)

    logger.debug(f'Dose limits set to {roilimits}')
    return roilimits


def RunOptimizations(show_dialog=True, iterations=None, cycles=None):
    plan = get_current("Plan")
    beam_set = get_current("BeamSet")

    bopt = BulkOptimizer(plan=plan, beam_set=beam_set,
                         iterations=iterations, cycles=cycles)

    if show_dialog:
        run_opt = bopt.show_options_dialog()
    else:
        run_opt = True

    while run_opt:
        run_opt = False
        try:
            bopt.run()
            return

        except Warning as e:
            logger.warning("{}".format(e), exc_info=True)

            Show_OK(e.args[1], "Optimization Failed")
        except ObjectiveError as e:
            if not show_dialog:
                run_opt = True
                continue

            caption = "Optimization failed. Retry?"
            message = ('Optimization failed due to conflicting ROI goals:\n'
                       f'{e.args[1]}\n'
                       'Try again without scaling those goals?')
            run_opt = Show_YesNo(message, caption, ontop=True)


if __name__ == '__main__':
    log_fmt = ('%(asctime)s: %(name)s.%(funcName)s:%(lineno)d'
               ' - %(levelname)s: %(message)s')

    logging.basicConfig(format=log_fmt, stream=sys.stdout,
                        force=True)

    RunOptimizations()
