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
        logging.info("J: Harvest-klipper initiated!")
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object("gcode")
        self.motion_report = self.printer.load_object(config, "motion_report")
        self.virtual_sdcard = self.printer.lookup_object("virtual_sdcard")

        _ = config.get("serial", "")

        self.print_job_id = STANDARD_ID
        self.new_print_job_flag = False
        self.layer_counter = 0

    def get_status(self, eventtime) -> dict:
        """This function is present in most modules and allows to read out the status of this module
        over different queries. Needed for passing down the print job id to harvest

        :param eventtime: The time of when the get_status was actually called
        :type eventtime: ?
        :return: Dictionary of the eventtime, and the name of this module (as a placeholder)
        :rtype: dict
        """
        return {
            "eventtime": eventtime,
            "current_print_id": self.print_job_id,
            "time_since_last_gcode": self.reactor.monotonic()
            - self.batches["gcode"]["last_timestamp"],
            "last_gcode_line": self.batches["gcode"]["last"],
            "current_layer_nr": self.layer_counter,
        }

    def process_gcode(self, line):
        """Processes the gcode line and triggers the _print_start_processing function

        :param line: The gcode line that is to be processed
        :type line: str
        """
        logging.info(f"J: Harvest-klipper process gcode triggered with {line}")
        # self._print_start_processing(line)

    def _respond_raw(self, msg: str) -> None:
        """Script that is triggered if the gcode object sends out a message. If a file is done printing, the
        batch information that is still in the buffer will be stored to a file.

        :param msg: the message sent out by the gcode object
        :type msg: str
        """
        # logging.info(f"J: Harvest-klipper respond raw triggered with {msg}")
        if msg == "Done printing file":
            logging.info(f"J: Harvest-klipper done - write last batch")
            for i in self.all_batch_names:
                self._write_batch_to_file(batch_name=i)

    def _print_start_processing(self, line):
        if "SDCARD_PRINT_FILE" in line:
            self.layer_counter = 0
            try:
                with open(
                    os.path.join(os.path.expanduser("~"), "runnerState.json"), "r"
                ) as f:
                    data = json.load(f)
                    self.print_job_id = data["currentPrintJobSort"]
            except Exception as e:
                logging.error(f"J: Harvest-klipper: {e}")
                self.print_job_id = STANDARD_ID
            else:
                logging.info(
                    f"J: Harvest-klipper: new print job started with id: {self.print_job_id}"
                )
            self.new_print_job_flag = True
        else:
            self.new_print_job_flag = False
        if ";LAYER_CHANGE" in line:
            self.layer_counter += 1

    def _correct_printer_id_while_not_printing(self, eventtime):
        if not self.virtual_sdcard.is_active():
            self.print_job_id = STANDARD_ID
            self.new_print_job_flag = True
        else:
            self.new_print_job_flag = False
        return eventtime + self.get_position_time_delta

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
