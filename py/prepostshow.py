#!/usr/bin/env python
#
# Licensed under the BSD license.  See full license in LICENSE file.
# http://www.lightshowpi.com/
#
# Author: Todd Giles (todd@lightshowpi.com)
# Author: Chris Usey (chris.usey@gmail.com)
"""
Preshow and Postshow functionality for the lightshows.

Your lightshow can be configured to have a "preshow" before each
individual song is played or an "postshow" after each individual
song is played.  See the default configuration file for more
details on configuring your pre or post show.

Sample usage (to test your preshow or postshow configuration):

sudo python prepostshow.py "preshow"
or
sudo python prepostshow.py "postshow"
"""

import logging
import os
import time
import subprocess
import signal
import sys

import configuration_manager as cm
import hardware_controller as hc

def check_state():
    """
    Check State file

    Check the state file to see if play now requested
    """
    # refresh state
    cm.load_state()
    if int(cm.get_state('play_now', 0)):
        # play now requested!
        return True
    return False

class PrePostShow(object):
    """
    The PreshowPostshow class handles all pre-show and post-show logic

    Typical usage to simply play the default configured preshow_configuration:
    or postshow_configuration:

    PrePostShow("preshow").execute()
    PrePostShow("postshow").execute()
    """
    done, play_now_interrupt = range(2)

    def __init__(self, show="preshow"):
        hc.initialize()
        self.config = cm.lightshow()[show]
        self.show = show
        self.audio = None

    def set_config(self, config):
        """Set a new configuration to use for the preshow"""
        self.config = config

    def execute(self):
        """
        Execute the pre/post show as defined by the current config

        Returns the exit status of the show, either done if the
        show played to completion, or play_now_interrupt if the
        show was interrupted by a play now command.
        """
        # Is there a show to launch?
        if self.config == None:
            return PrePostShow.done
        
        # Is the config a script or a transition based show
        # launch the script if it is
        if not isinstance(self.config, dict) and os.path.exists(self.config):
            logging.debug("Launching external script " + self.config + " as " \
                + self.show)
            return self.start_script()

        # start the audio if there is any
        self.start_audio()

        if 'transitions' in self.config:
            try:
                # display transition based show
                for transition in self.config['transitions']:
                    start = time.time()
                    if transition['type'].lower() == 'on':
                        hc.turn_on_lights(True)
                    else:
                        hc.turn_off_lights(True)
                    logging.debug('Transition to ' + transition['type'] + ' for ' \
                        + str(transition['duration']) + ' seconds')

                    if 'channel_control' in transition:
                        channel_control = transition['channel_control']
                        for key in channel_control.keys():
                            mode = key
                            channels = channel_control[key]
                            for channel in channels:
                                if mode == 'on':
                                    hc.turn_on_light(int(channel) - 1, 1)
                                elif mode == 'off':
                                    hc.turn_off_light(int(channel) - 1, 1)
                                else:
                                    logging.error("Unrecognized channel_control mode "
                                                "defined in preshow_configuration " \
                                                    + str(mode))
                    # hold transition for specified time
                    while transition['duration'] > (time.time() - start):
                        # check for play now
                        if check_state():
                            # kill the audio playback if playing
                            if self.audio:
                                os.killpg(self.audio.pid, signal.SIGTERM)
                                self.audio = None
                            return PrePostShow.play_now_interrupt
                        time.sleep(0.1)
            except:
                pass
        
        # hold show until audio has finished if we have audio
        # or audio is not finished
        return_value = self.hold_for_audio()

        return return_value

    def start_audio(self):
        """Start audio plaback if there is any"""
        if "audio_file" in self.config and self.config['audio_file'] != None:
            audio_file = self.config['audio_file']
            self.audio = subprocess.Popen(["mpg123", "-q", audio_file])
            logging.debug("Starting " + self.show + " audio file " + self.config['audio_file'])

    def hold_for_audio(self):
        """hold show until audio has finished"""
        if self.audio:
            while self.audio.poll() == None:
                # check for play now
                if check_state():
                    # kill the audio playback if playing
                    os.killpg(self.audio.pid, signal.SIGTERM)
                    self.audio = None
                    return PrePostShow.play_now_interrupt
                time.sleep(0.1)
        return PrePostShow.done

    def start_script(self):
        """Start a seperate script to control the lights"""
        return_value = PrePostShow.done
        hc.clean_up()
        
        # make a copy of the path
        path = list(sys.path)

        # insert script location and hardware_controller location into path
        sys.path.insert(0, cm.HOME_DIR + "/py")
        sys.path.insert(0, os.path.split(self.config)[0])

        # create environment for script to run in
        environment = os.environ.copy()
        environment['PYTHONPATH'] = ':'.join(sys.path)

        #run script
        show = subprocess.Popen('python ' + self.config,
                                preexec_fn=os.setsid,
                                shell=True,
                                close_fds=True,
                                env=environment)

        # check for user interrupt
        while show.poll() is None:
            if check_state():
                # Skip out on the rest of the show if play now requested!
                os.killpg(show.pid, signal.SIGTERM)
                return_value = PrePostShow.play_now_interrupt
                break

            # Check once every ~ .1 seconds to break out
            time.sleep(0.1)

        # restore path
        sys.path[:] = path

        # insure clean up just in case the user forgot to do it
        hc.clean_up()

        return return_value

if __name__ == "__main__":
    show_to_call = 'preshow'

    if len(sys.argv) > 1:
        show_to_call = sys.argv[1]

    PrePostShow(show_to_call).execute()
