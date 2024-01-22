import logging
import os
import importlib
import threading
import sys
import subprocess
import random

# setting path
sys.path.append("/home/pi/harvest")
from shutdown_object import ShutdownObject

GCODE_FOLDER_PATH = "/home/pi/harvest/output"


class GcodeTracker:
    """Custom module used to collect information about gcode (and potentially any other printer-related data) at the time a gcode line is processed
    by the gcode.py file (refer to the diagram contained in the harvest repository for more information on this).
    """

    def __init__(self, config):
        """Sets up the module and starts the harvest_main.py script (if possible)

        :param config: contains the information from the config file for the 'gcode_tracker printer' section
        :type config: ?
        :raises ValueError: If the harvest folder is not available (i.e. the repository is not present or installed in a wrong location) an error is raised
        - this should avoid useless collection of gcode data with no way of matching it with other data.
        """
        logging.info("J: GcodeTracker initiated!")
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object("gcode")

        _ = config.get("serial", "")

        self.gcode.register_output_handler(self._respond_raw)
        self.printer.register_event_handler("klippy:shutdown", self._handle_shutdown)
        self.printer.register_event_handler("klippy:disconnect", self._handle_shutdown)

        self.batch = []
        self.last_cmd = None
        self.counter = 0
        self.batch_counter = 0
        if not os.path.exists("/home/pi/harvest"):
            raise ValueError("harvest not installed - no gcode tracking possible!")
        self._create_output_folder()
        self.print_job_id = "NO_ID_KLIPPER"
        self.new_print_job_flag = False
        self.gcode_file_path = os.path.join(
            GCODE_FOLDER_PATH, f"{self.print_job_id}_gcode_{self.batch_counter}.csv"
        )

        script_name = "/home/pi/harvest/harvest_main.py"
        try:
            with open("/home/pi/harvest/harvest.log", "a+") as log_file:
                process = subprocess.Popen(
                    ["/home/pi/harvest-env/bin/python", script_name],
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    shell=False,
                )
                logging.info(
                    f"Started {script_name} in a new process. Process ID: {process.pid}"
                )
        except Exception as e:
            logging.info(f"Error starting {script_name}: {e}")

        self.timer = self.reactor.register_timer(
            self._get_printer_position, self.reactor.NOW
        )

    def _get_printer_position(self, eventtime):
        try:
            logging.info(f"J: gcode_tracker: timestamp: {self.reactor.monotonic()}, motion report: {self.printer.lookup_object('motion_report').get_status(eventtime)}")
        except Exception as e:
            logging.info(f"J: gcode_tracker get printer position: {e}")
        return eventtime + 0.1


    def get_status(self, eventtime) -> dict:
        """This function is present in most modules and allows to read out the status of this module
        over different queries. Not needed, but included for the sake of completness.

        :param eventtime: The time of when the get_status was actually called
        :type eventtime: ?
        :return: Dictionary of the eventtime, the last gcode command that sent to this module with its count number.
        :rtype: dict
        """
        return {
            "eventtime": eventtime,
            "current_gcode_line": self.last_cmd,
            "current_gcode_line_count": self.counter,
            "current_print_id": self.print_job_id,
        }

    def _respond_raw(self, msg: str) -> None:
        """Script that is triggered if the gcode objects sends out a message. If a file is done printing, the
        gcode information that is still in the buffer will be stored to a file.

        :param msg: the message sent out by the gcode object
        :type msg: str
        """
        logging.info(f"J: Gcode tracker respond raw triggered with {msg}")
        if msg == "Done printing file":
            logging.info(f"J: Gcode tracker done - write last batch")
            self._write_gcommand_batch_to_file()

    def _handle_shutdown(self) -> None:
        """Shutdown function that writes gcode information that is still in the buffer to a file"""
        logging.info(f"J: Gcode tracker handling shutdown - writing last batch")
        self._write_gcommand_batch_to_file()

    def _create_output_folder(self) -> None:
        """If the destination for storing the gcode information is not existing yet, creat the respective folder"""
        if not os.path.exists(GCODE_FOLDER_PATH):
            os.mkdir(os.path.join(GCODE_FOLDER_PATH))
            logging.info("J: output folder for gcode tracking created")

    def _write_gcommand_batch_to_file(self) -> None:
        """Upon execution, write all the gcode information currently present in the buffer to the output file and reset the batch"""
        if len(self.batch) > 0:
            logging.info("J: Writing batch info to file")
            open(self.gcode_file_path, "a+").writelines(self.batch)
            logging.info("J: Writing batch info to file - done")
            self.batch = []
            self.batch_counter += 1
            self.gcode_file_path = os.path.join(
                GCODE_FOLDER_PATH, f"{self.print_job_id}_gcode_{self.batch_counter}.csv"
            )

    def add_to_batch(self, cmd: str) -> None:
        """Adds a new gcode command (line) to the buffer with the current (event)time. Here, also additional printer-related information could be added!
        If a new print job is started, respectively a new print_job_id will will be passed, the last command and counter is resetted and the
        path to the output file is adjusted accordingly

        :param cmd: the gcode line that should be stored
        :type cmd: str
        """
        self._print_start_processing(cmd)
        if self.new_print_job_flag:
            self._write_gcommand_batch_to_file()
            self.last_cmd = ""
            self.counter = 0
            self.batch_counter = 0
            self.gcode_file_path = os.path.join(
                GCODE_FOLDER_PATH, f"{self.print_job_id}_gcode_{self.batch_counter}.csv"
            )
        else:
            self.last_cmd = cmd
            self.counter += 1
        self.batch.append(f"{self.counter},{self.reactor.monotonic()},{cmd}\n")
        if len(self.batch) >= 1000:
            self._write_gcommand_batch_to_file()

    def _print_start_processing(self, line):
        if "SDCARD_PRINT_FILE" in line:
            tmp = line.split("FILENAME=")[1].replace('"', "")
            self.print_job_id = f"{tmp}_{self.reactor.monotonic()}_{random.randint(100000000,999999999)}"
            self.new_print_job_flag = True
        else:
            self.new_print_job_flag = False


def load_config_prefix(config):
    return GcodeTracker(config)
