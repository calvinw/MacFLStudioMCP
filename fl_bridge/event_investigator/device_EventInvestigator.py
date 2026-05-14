#name=Event Investigator
#url=https://github.com/calvinw/MacFLStudioMCP
#description=Logs all FL Studio events to the Script Output console and a log file

"""
FL Studio Event Investigator
============================
Logs every event to both the Script Output console and a log file next to this script.

View console:  Tools → Script Output (Ctrl+L → Script tab)
View log file: Hardware/Event Investigator/events.log  (tail -f it from a terminal)
"""

import os
import sys
from pathlib import Path

import midi
import channels
import mixer
import patterns
import playlist
import ui
import transport
import device


def _log_path():
    if sys.platform == "darwin":
        base = Path.home() / "Documents" / "Image-Line" / "FL Studio" / "Settings"
    elif sys.platform == "win32":
        base = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Documents" / "Image-Line" / "FL Studio" / "Settings"
    else:
        base = Path.home() / "Documents" / "Image-Line" / "FL Studio" / "Settings"
    return base / "Hardware" / "Event Investigator" / "events.log"


LOG_PATH = _log_path()

event_count = 0
_log_file = None


def _open_log():
    global _log_file
    try:
        # File must be pre-created by install script — FL's audit hook blocks new-file creation
        _log_file = open(LOG_PATH, "a")
    except Exception as e:
        print(f"[EventInvestigator] Could not open log: {e}")
        _log_file = None


def _log(line):
    print(line)
    if _log_file:
        try:
            _log_file.write(line + "\n")
            _log_file.flush()
        except Exception:
            pass


def print_event(name, details=""):
    global event_count
    event_count += 1
    _log(f"[{event_count:04d}] {name}")
    if details:
        _log(f"     {details}")


def _fmt(eventData):
    parts = []
    for attr in ("handled", "timestamp", "status", "data1", "data2", "port"):
        if hasattr(eventData, attr):
            val = getattr(eventData, attr)
            parts.append(f"{attr}={val!r}" if attr != "status" else f"status=0x{val:02X}")
    return ", ".join(parts)


# =============================================================================
# INIT / DEINIT
# =============================================================================

def OnInit():
    _open_log()
    _log("=" * 60)
    _log("EVENT INVESTIGATOR STARTED")
    _log(f"Log: {LOG_PATH}")
    _log("=" * 60)
    print_event("OnInit")
    _log(f"     Device: {device.getName() if device.isAssigned() else 'No output assigned'}")
    if device.isAssigned():
        _log(f"     Port: {device.getPortNumber()}")


def OnDeInit():
    print_event("OnDeInit", f"Total events: {event_count}")
    _log("=" * 60)
    _log("EVENT INVESTIGATOR STOPPED")
    _log("=" * 60)
    if _log_file:
        try:
            _log_file.close()
        except Exception:
            pass


def OnFirstConnect():
    print_event("OnFirstConnect")


# =============================================================================
# MIDI
# =============================================================================

def OnMidiIn(eventData):
    print_event("OnMidiIn", _fmt(eventData))


def OnMidiMsg(eventData):
    s = eventData.status & 0xF0
    names = {0x80: "Note Off", 0x90: "Note On", 0xA0: "Key Pressure",
             0xB0: "Control Change", 0xC0: "Program Change",
             0xD0: "Channel Pressure", 0xE0: "Pitch Bend"}
    print_event(f"OnMidiMsg ({names.get(s, 'Unknown')})", _fmt(eventData))


def OnSysEx(eventData):
    print_event("OnSysEx", f"length={len(eventData.sysex) if hasattr(eventData, 'sysex') else 0}")


def OnNoteOn(eventData):
    print_event("OnNoteOn",
                f"note={eventData.note}, vel={eventData.velocity}, "
                f"ch={eventData.midiChan}, port={eventData.port}")


def OnNoteOff(eventData):
    print_event("OnNoteOff",
                f"note={eventData.note}, vel={eventData.velocity}, "
                f"ch={eventData.midiChan}, port={eventData.port}")


def OnControlChange(eventData):
    print_event("OnControlChange",
                f"CC={eventData.controlNum}, val={eventData.controlVal}, "
                f"ch={eventData.midiChan}, port={eventData.port}")


def OnProgramChange(eventData):
    print_event("OnProgramChange", f"program={eventData.progNum}, ch={eventData.midiChan}")


def OnPitchBend(eventData):
    print_event("OnPitchBend", f"value={eventData.pitchBend}, ch={eventData.midiChan}")


def OnKeyPressure(eventData):
    print_event("OnKeyPressure", f"note={eventData.note}, pressure={eventData.pressure}")


def OnChannelPressure(eventData):
    print_event("OnChannelPressure", f"pressure={eventData.pressure}")


def OnMidiOutMsg(eventData):
    print_event("OnMidiOutMsg",
                f"status=0x{eventData.status:02X}, data1={eventData.data1}, "
                f"data2={eventData.data2}, midiId={eventData.midiId}, "
                f"ch={eventData.midiChan}")


# =============================================================================
# PROJECT
# =============================================================================

def OnProjectLoad(status):
    names = {0: "PL_Start", 100: "PL_LoadOk", 101: "PL_LoadError"}
    print_event("OnProjectLoad", names.get(status, f"status={status}"))


# =============================================================================
# REFRESH
# =============================================================================

def OnRefresh(flags):
    flag_map = {
        1:     "Mixer_Sel",
        2:     "Mixer_Display",
        4:     "Mixer_Controls",
        16:    "RemoteLinks",
        32:    "FocusedWindow",
        64:    "Performance",
        256:   "LEDs",
        512:   "RemoteLinkValues",
        1024:  "Patterns",
        2048:  "Tracks",
        4096:  "ControlValues",
        8192:  "Colors",
        16384: "Names",
        32768: "ChannelRackGroup",
        65536: "ChannelEvent",
    }
    active = [name for val, name in flag_map.items() if flags & val]
    detail = " | ".join(active) if active else f"flags={flags}"

    if flags & 32:
        form_id = ui.getFocusedFormID()
        win = {0: "Mixer", 1: "Channel Rack", 2: "Playlist", 3: "Piano Roll", 4: "Browser"}
        detail += f"  →  window={win.get(form_id, f'id={form_id}')} '{ui.getFocusedFormCaption()}'"

    if flags & 256:
        led = []
        if transport.isPlaying():   led.append("PLAYING")
        if transport.isRecording(): led.append("RECORDING")
        led.append("Song" if transport.getLoopMode() == 1 else "Pattern")
        beat = {0: "off", 1: "bar", 2: "beat"}.get(transport.getHWBeatLEDState(), "?")
        led.append(f"beat={beat}")
        detail += f"  →  [{' | '.join(led)}]"

    print_event("OnRefresh", detail)


def OnDoFullRefresh():
    print_event("OnDoFullRefresh")


# =============================================================================
# UI / STATE
# =============================================================================

def OnUpdateBeatIndicator(value):
    print_event("OnUpdateBeatIndicator", {0: "off", 1: "bar", 2: "beat"}.get(value, str(value)))


def OnDisplayZone():
    print_event("OnDisplayZone", f"zone={playlist.getDisplayZone()}")


def OnUpdateLiveMode(lastTrack):
    print_event("OnUpdateLiveMode", f"lastTrack={lastTrack}")


def OnWaitingForInput():
    print_event("OnWaitingForInput")


def OnSendTempMsg(message, duration):
    print_event("OnSendTempMsg", f"'{message}' ({duration}ms)")


# =============================================================================
# MIXER / CHANNEL
# =============================================================================

def OnDirtyMixerTrack(index):
    if index >= 0:
        print_event("OnDirtyMixerTrack", f"index={index}, name='{mixer.getTrackName(index)}'")
    else:
        print_event("OnDirtyMixerTrack", "all tracks")


def OnDirtyChannel(index, flag):
    flag_names = {0: "CE_New", 1: "CE_Delete", 2: "CE_Replace", 3: "CE_Rename", 4: "CE_Select"}
    fname = flag_names.get(flag, f"flag={flag}")
    if index >= 0:
        print_event("OnDirtyChannel",
                    f"index={index}, name='{channels.getChannelName(index)}', {fname}")
    else:
        print_event("OnDirtyChannel", f"all channels, {fname}")


# =============================================================================
# IDLE — fires constantly; uncomment only when debugging timing
# =============================================================================

def OnIdle():
    pass


def OnUpdateMeters():
    pass
