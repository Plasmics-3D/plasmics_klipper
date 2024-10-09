import logging
import os
import sys
import subprocess
import random
import json

STANDARD_ID = "NO_ID_HARVEST"


class HarvestKlipper:
    """Custom module used to collect information about gcode and other klipper-related information (refer to the diagram contained in the harvest repository for more information on this)."""

    def __init__(self, config):
        """Sets up the module and starts the harvest_main.py script (if possible)
        :param config: contains the information from the config file for the 'harvest_klipper' section
        :type config: ?
        :raises ValueError: If the harvest folder is not available (i.e. the repository is not present or installed in a wrong location) an error is raised
        - this should avoid useless collection of data with no way of matching it with other data.
        """
        self.standard_status_object = {
            "eventtime": 0,
            "current_print_id": STANDARD_ID,
            "print_start_time": 0,
            "current_time": 0,
            "current_layer_nr": 0,
            "current_gcode_line": "",
            "current_gcode_position": 0,
            "current_toolhead_position": 0,
        }
        logging.info("J: Harvest-klipper initiated!")
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object("gcode")
        self.motion_report = self.printer.load_object(config, "motion_report")
        self.virtual_sdcard = self.printer.lookup_object("virtual_sdcard")
        self.status_object = self.standard_status_object.copy()
        self.gcode_counter = 0

    def get_status(self, eventtime) -> dict:
        """This function is present in most modules and allows to read out the status of this module
        over different queries. Needed for passing down the print job id to harvest

        :param eventtime: The time of when the get_status was actually called
        :type eventtime: ?
        :return: Dictionary of the eventtime, and the name of this module (as a placeholder)
        :rtype: dict
        """
        self.status_object["eventtime"] = eventtime
        return self.status_object

    def process_gcode(self, line):
        """Processes the gcode line and triggers the _print_start_processing function

        :param line: The gcode line that is to be processed
        :type line: str
        """
        if "SDCARD_PRINT_FILE" in line:
            self.gcode_counter = 0
            # reset the status object
            self.status_object = self.standard_status_object.copy()
            try:
                with open(
                    os.path.join(os.path.expanduser("~"), "runnerState.json"), "r"
                ) as f:
                    data = json.load(f)
                    self.status_object["current_print_id"] = data["currentPrintJobSort"]
            except Exception as e:
                logging.error(f"J: Harvest-klipper: {e}")
            else:
                logging.info(
                    f"Harvest-klipper: new print job started with id: {self.status_object['current_print_id']}"
                )
            self.status_object["print_start_time"] = self.reactor.monotonic()
        elif ";LAYER:" in line:
            self.status_object["current_layer_nr"] = int(line.split(":")[1])

        self.status_object["current_gcode_line"] = line
        self.status_object["current_gcode_position"] = self.gcode_counter
        self.status_object["current_time"] = self.reactor.monotonic()
        self.status_object["current_toolhead_position"] = self._get_printer_position(
            self.status_object["current_time"]
        )
        self.gcode_counter += 1

    def _get_printer_position(self, eventtime):
        if self.virtual_sdcard.is_active():
            try:
                status = self.motion_report.get_status(eventtime)
                current_position = ",".join(
                    [str(round(i, 3)) for i in list(status["live_position"])]
                )
                line = f"{round(eventtime,5)},{current_position},{round(status['live_velocity'],3)},{round(status['live_extruder_velocity'],3)}"
            except Exception as e:
                logging.error(f"J: Harvest-klipper printer position ERROR: {e}")
        return line


def load_config(config):
    return HarvestKlipper(config)
