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

OUTPUT_PATH = "/home/pi/harvest/output"


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
        self.motion_report = self.printer.lookup_object("motion_report")
        self.virtual_sdcard = self.printer.lookup_object("virtual_sdcard")
        self.ino_sensors = []

        _ = config.get("serial", "")
        self.get_position_time_delta = config.getfloat("get_position_time_delta", 0.1)
        self.get_ino_time_delta = config.getfloat("get_ino_time_delta", 0.1)

        self.gcode.register_output_handler(self._respond_raw)
        self.printer.register_event_handler("klippy:connect", self._connect)
        self.printer.register_event_handler("klippy:shutdown", self._handle_shutdown)
        self.printer.register_event_handler("klippy:disconnect", self._handle_shutdown)

        if not os.path.exists("/home/pi/harvest"):
            raise ValueError("harvest not installed - no data collection possible!")
        self._create_output_folder()
        self.print_job_id = "NO_ID_KLIPPER"
        self.new_print_job_flag = False

        self.batches = {
            "gcode": {
                "counter": 0,
                "batch": [],
                "batch_counter": 0,
                "last": None,
                "file_path": os.path.join(
                    OUTPUT_PATH,
                    f"{self.print_job_id}_gcode_{0}.csv",
                ),
            },
            "toolheadposition": {
                "counter": 0,
                "batch": [],
                "batch_counter": 0,
                "last": None,
                "file_path": os.path.join(
                    OUTPUT_PATH,
                    f"{self.print_job_id}_toolheadposition_{0}.csv",
                ),
            },
            "ino": {
                "counter": 0,
                "batch": [],
                "batch_counter": 0,
                "last": None,
                "file_path": os.path.join(
                    OUTPUT_PATH,
                    f"{self.print_job_id}_ino_{0}.csv",
                ),
            },
        }

        self.all_batch_names = list(self.batches.keys())

        # start harvest
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

        # get the calculated position of the printer every get_position_time_delta ms
        self.printer_position_timer = self.reactor.register_timer(
            self._get_printer_position, self.reactor.NOW
        )

        self.ino_timer = self.reactor.register_timer(self._get_ino, self.reactor.NOW)

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
        }

    def _connect(self) -> None:
        """Upon connect, get the available INO sensors"""
        self.ino_sensors = [
            i[1]
            for i in self.printer.lookup_objects("pla_ino_sensor")
            if i[1] is not None
        ]
        logging.info(f"J: INO sensor registered: {self.ino_sensors}")

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

    def _handle_shutdown(self) -> None:
        """Shutdown function that writes batch information that is still in the buffer to a file"""
        logging.info(f"J: Harvest-klipper handling shutdown - writing last batch")
        for i in self.all_batch_names:
            self._write_batch_to_file(batch_name=i)

    def _print_start_processing(self, line):
        if "SDCARD_PRINT_FILE" in line:
            tmp = line.split("FILENAME=")[1].replace('"', "")
            self.print_job_id = f"{tmp}_{self.reactor.monotonic()}_{random.randint(100000000,999999999)}"
            self.new_print_job_flag = True
        else:
            self.new_print_job_flag = False

    def _create_output_folder(self) -> None:
        """If the destination for storing the batch information is not existing yet, creat the respective folder"""
        if not os.path.exists(OUTPUT_PATH):
            os.mkdir(os.path.join(OUTPUT_PATH))
            logging.info(
                "J: Harvest-klipper: output folder for data collection created"
            )

    def _write_batch_to_file(self, batch_name: str) -> None:
        """Upon execution, write all the batch information currently present in the buffer to the output file and reset the batch

        :param batch_name: the name of the batch that should be written to file
        :type batch_name: str"""

        current_batch = self.batches[batch_name]
        if len(current_batch["batch"]) > 0:
            logging.info(
                f"J: Writing batch {batch_name} to file {current_batch['file_path']}"
            )
            open(current_batch["file_path"], "a+").writelines(current_batch["batch"])
            logging.info(f"J: Writing batch {batch_name} to file - done")
            current_batch["batch"] = []
            current_batch["batch_counter"] += 1
            current_batch["file_path"] = os.path.join(
                OUTPUT_PATH,
                f"{self.print_job_id}_{batch_name}_{current_batch['batch_counter']}.csv",
            )

    def add_to_batch(self, batch_name: str, entry: str) -> None:
        """Adds a new entry to the a batch with the current (event)time.
        If a new print job is started, respectively a new print_job_id will will be passed, the last command and counter is resetted and the
        path to the output file is adjusted accordingly

        :param batch_name: the name of the batch were the entry should be added to
        :type batch_name: str
        :param entry: the entry element that should be stored
        :type entry: str
        """
        self._print_start_processing(entry)
        if self.new_print_job_flag:
            for i in self.all_batch_names:
                current_batch = self.batches[i]
                self._write_batch_to_file(batch_name=i)
                current_batch["last"] = ""
                current_batch["counter"] = 0
                current_batch["batch_counter"] = 0
                current_batch["file_path"] = os.path.join(
                    OUTPUT_PATH,
                    f"{self.print_job_id}_{i}_{0}.csv",
                )
        try:
            current_batch = self.batches[batch_name]
        except Exception as e:
            logging.error(f"J: Harvest-klipper printer position ERROR: {e}")
        else:
            current_batch["last"] = entry
            current_batch["counter"] += 1
            current_batch["batch"].append(f"{current_batch['counter']},{entry}\n")
            if len(current_batch["batch"]) >= 1000:
                self._write_batch_to_file(batch_name=batch_name)

    def _get_printer_position(self, eventtime):
        if self.virtual_sdcard.is_active():
            try:
                # logging.info(
                #     f"J: Harvest-klipper: timestamp: {self.reactor.monotonic()},{eventtime},{self.motion_report.get_status(eventtime)}"
                # )
                status = self.motion_report.get_status(eventtime)
                current_position = ",".join(
                    [str(round(i, 3)) for i in list(status["live_position"])]
                )
                line = f"{eventtime},{current_position},{status['live_velocity']},{status['live_extruder_velocity']}"
                self.add_to_batch(batch_name="toolheadposition", entry=line)
            except Exception as e:
                logging.error(f"J: Harvest-klipper printer position ERROR: {e}")
        return eventtime + self.get_position_time_delta

    def _get_ino(self, eventtime):
        if self.virtual_sdcard.is_active():
            for i in self.ino_sensors:
                try:
                    status = i.get_status(eventtime)
                    line = f"{status['last_debug_timestamp']},{status['last_debug_message']}"
                    self.add_to_batch(batch_name="ino", entry=line)

                    # logging.info(f"J: INO readout: {eventtime},{status['last_debug_timestamp']},{status['last_debug_message']}")
                except Exception as e:
                    logging.error(f"J: Harvest-klipper ino ERROR: {e}")
        return eventtime + self.get_position_time_delta


def load_config(config):
    return HarvestKlipper(config)
