# Control of INO hotend
#
# Copyright (C) 2023  Johannes Zischg <johannes.zischg@plasmics.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging
import serial
from . import bus
from serial import SerialException
from queue import Queue, Empty

SERIAL_TIMER = 0.1


class PLA_INO_Sensor:
    """Custom class for the PLA_INO sensor"""
    def __init__(self, config):
        """The sensor is initialized, this includes especially
        - the registration for specific events (and how to handle those)
        - the configuration of INO specific G_code commands - this happens only with the first INO Sensor

        :param config: config file passed down from the heater
        :type config: ?
        """
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object("gcode")
        self.reactor = self.printer.get_reactor()
        self.name = config.get_name().split()[-1]
        logging.info(f"J: INO Sensor self.name: {self.name}")
        self.printer.add_object("pla_ino_sensor " + self.name, self)
        self.heater = None
        self.serial = None
        self.read_timer = None
        self.temp = 0.0
        self.read_buffer = ""
        self.read_queue = Queue()
        self.write_timer = None
        self.write_queue = Queue()

        # To avoid restart of ino sensor without being initialized again
        self.once_in_a_lifetime_connect = True

        self.printer.register_event_handler("klippy:connect", self._handle_connect)

        self.printer.register_event_handler(
            "klippy:disconnect", self._handle_disconnect
        )
        self.printer.register_event_handler("klippy:shutdown", self._handle_shutdown)

        # add the gcode commands
        logging.info(f"J: gcode ready handlers: {self.gcode.ready_gcode_handlers.keys()}")
        if "INO_FREQUENCY" in self.gcode.ready_gcode_handlers.keys():
            logging.info("J: INO Frequency already defined!")
        else:
            self.gcode.register_command(
                "INO_FREQUENCY", self.cmd_INO_FREQUENCY, desc=self.cmd_INO_FREQUENCY_help
            )
            self.gcode.register_command(
                "INO_PID_TUNE", self.cmd_INO_PID_TUNE, desc=self.cmd_INO_PID_TUNE_help
            )
            self.gcode.register_command(
                "INO_READ_PID_VALUES",
                self.cmd_INO_READ_PID_VALUES,
                desc=self.cmd_INO_READ_PID_VALUES_help,
            )
            self.gcode.register_command(
                "INO_SET_PID_VALUES",
                self.cmd_INO_SET_PID_VALUES,
                desc=self.cmd_INO_SET_PID_VALUES_help,
            )
            self.gcode.register_command(
                "INO_RESET_ERROR_FLAGS",
                self.cmd_INO_RESET_ERROR_FLAGS,
                desc=self.cmd_INO_RESET_ERROR_FLAGS_help,
            )
            self.gcode.register_command(
                "INO_DEBUG_OUT", self.cmd_INO_DEBUG_OUT, desc=self.cmd_INO_DEBUG_OUT_help
            )
            logging.info(f"J: All Gcode commands added.")

    def make_heater_known(self, heater, config):
        """This function is called once the heater is set up - acts as a handshake between heater and sensor
        it passes the config file again and the 'load_config' function is called

        :param heater: heater object the sensor belongs to
        :type heater: heater object
        :param config: configuration file for the heater object
        :type config: ?
        """
        logging.info(f"J: heater registered in sensor: {heater}")
        self.heater = heater
        self.load_config(config)

    def load_config(self, config):
        """Reads out the config file and sets parameters necessary for the serial connection to the ino boards

        :param config: config file
        :type config: ?
        """
        self.baud = 115200
        self.serial_port = config.get("serial")
        self.report_time = self.heater.pwm_delay
        self.pid_Kp = self.heater.pid_Kp
        self.pid_Ki = self.heater.pid_Ki
        self.pid_Kd = self.heater.pid_Kd

        logging.info(
            f"J: sensor load_config done {self.baud},{self.serial_port},{self.report_time}"
        )
        self.sample_timer = self.reactor.register_timer(
            self._sample_PLA_INO, self.reactor.NOW
        )

    def _handle_connect(self):
        if self.serial is None:
            self._init_PLA_INO()

    def _handle_disconnect(self):
        self.disconnect()

    def _handle_shutdown(self):
        logging.info("J: Ino heater shutting down")
        self.disconnect()

    def disconnect(self):
        """Once disconnect is called, the sensor will start shutting down.
        This includes:
        - Setting the temperature of the INO heater to 0
        - closing of the serial connection to the INO board
        - Unregisters the timers from this sensor
        """
        try:
            s = "s 0"
            self.write_queue.put(s)
            self.serial.close()
            self.serial = None
            logging.info("Serial port closed due to disconnect.")
        except serial.SerialException:
            logging.exception("J: Serial port already closed before disconnection.")
        try:
            self.reactor.unregister_timer(self.read_timer)
            self.read_timer = None
        except:
            logging.info("J: Reactor read timer already unregistered before disconnection.")

        try:
            self.reactor.unregister_timer(self.write_timer)
            self.write_timer = None
        except:
            logging.info("J: Reactor write timer already unregistered before disconnection.")

        logging.info("J: Ino heater shut down complete.")
        self.once_in_a_lifetime_connect = False
        logging.info(f"J: Once in a lifetime connect set to {self.once_in_a_lifetime_connect} after disconnect.")

    def setup_minmax(self, min_temp, max_temp):
        self.min_temp = min_temp
        self.max_temp = max_temp

    def setup_callback(self, cb):
        self._callback = cb

    def get_report_time_delta(self):
        return self.report_time

    def get_status(self, eventtime):
        return {
            "temperature": round(self.temp, 2),
        }

    ### INO specifics
    def _sample_PLA_INO(self, eventtime):
        try:
            if self.serial is None:
                self._handle_connect()
            else:
                self.write_queue.put("r")
        except serial.SerialException:
            logging.error("Unable to communicate with Ino. Sample")
            self.temp = 0.1

        measured_time = self.reactor.monotonic()
        self._callback(measured_time, self.temp)
        return eventtime + self.report_time


    def _init_PLA_INO(self):
        """Initializes the INO by starting a serial connection to the ino board
        and sending the pid control parameters
        """
        if self.once_in_a_lifetime_connect:
            try:
                self.serial = serial.Serial(self.serial_port)
                logging.info("Connection to Ino successfull.")
            except serial.SerialException:
                logging.error("Unable to connect to Ino. Init")
                return

            with self.write_queue.mutex:
                self.write_queue.queue.clear()
            with self.read_queue.mutex:
                self.read_queue.queue.clear()

            logging.info("Ino queues cleared.")

            self.read_timer = self.reactor.register_timer(self._run_Read, self.reactor.NOW)
            self.write_timer = self.reactor.register_timer(
                self._run_Write, self.reactor.NOW
            )

            logging.info("Ino read/write timers started.")
            s = (
                "kp "
                + str(float(self.pid_Kp))
                + ";ki "
                + str(float(self.pid_Ki))
                + ";kd "
                + str(float(self.pid_Kd))
                + ";q"
            )
            self.write_queue.put(s)
        else:
            logging.info("J: Once in a lifetime connect already used up!")

    def _run_Read(self, eventtime):
        """Readout of the incoming messages over the serial port

        :param eventtime: current event time
        :type eventtime: ?
        :return: tell reactor not to call this function any more (if not available)
        :rtype: ?
        """
        # Do non-blocking reads from serial and try to find lines
        while True:
            try:
                raw_bytes = ""
                if self.serial.in_waiting > 0:
                    raw_bytes = self.serial.read()
                    # logging.info(f"J: Ino raw_bytes after read. {raw_bytes}")
            except SerialException:
                logging.error("Unable to communicate with Ino. Red")
                self.disconnect()
                return self.reactor.NEVER
            if len(raw_bytes):
                text_buffer = self.read_buffer + str(raw_bytes.decode())
                while True:
                    i = text_buffer.find("\x00")
                    if i >= 0:
                        line = text_buffer[0 : i + 1]
                        self.read_queue.put(line.strip())
                        text_buffer = text_buffer[i + 1 :]
                    else:
                        break
                self.read_buffer = text_buffer
            else:
                break

        # Process any decoded lines from the device
        while not self.read_queue.empty():
            try:
                # logging.info("Ino read from queue")
                text_line = self.read_queue.get_nowait()
            except Empty:
                pass

            zwischenspeicher_variable = text_line.rstrip("\x00")
            if str.isdigit(
                zwischenspeicher_variable.replace("-", "")
            ):  # check if can be converted to int (includes negative nr)
                self.temp = int(zwischenspeicher_variable) / 100
            elif str(zwischenspeicher_variable[:5]) == "ERROR":
                self.gcode.respond_info(
                    "INO ERROR:)\n" + str(zwischenspeicher_variable)
                )  # output to mainsail console
                logging.info(
                    "\n--------------------ERROR: ------------------------\n"
                    + str(zwischenspeicher_variable)
                    + "\n--------------------ERROR: ------------------------\n"
                )
            elif str(zwischenspeicher_variable[:5]) == "tick:":
                # for error output:
                start = zwischenspeicher_variable.find("err:")
                read_from_board = zwischenspeicher_variable[start + 4 :]
                read_from_board = read_from_board.zfill(
                    6
                )  # fill left of string with zeros if not 6 long
                read_from_board_out = read_from_board

                if read_from_board[0] == "1":
                    read_from_board_out = read_from_board_out + " | open circuit"
                if read_from_board[1] == "1":
                    read_from_board_out = read_from_board_out + " | no heartbeat"
                if read_from_board[2] == "1":
                    read_from_board_out = read_from_board_out + " | heating slow"
                if read_from_board[3] == "1":
                    read_from_board_out = read_from_board_out + " | heating fast"
                if read_from_board[4] == "1":
                    read_from_board_out = read_from_board_out + " | no temp read"

                self.gcode.respond_info(
                    "INO debug output:\n"
                    + str(zwischenspeicher_variable)
                    + "\n"
                    + str(read_from_board_out)
                )
                logging.info(
                    "\n--------------------INO debug output: ------------------------\n"
                    + str(zwischenspeicher_variable)
                    + "\n"
                    + str(read_from_board_out)
                    + "\n--------------------INO debug output: ------------------------\n"
                )
            else:
                self.gcode.respond_info(
                    "PID values, save these in printer.cfg in the [extruder] section and restart firmware:\n"
                    + str(zwischenspeicher_variable)
                )  # (TODO bessere beschreibung schreiben)
                logging.info(
                    "\n--------------------PID AUTOTUNED VALUES: ------------------------\n"
                    + str(zwischenspeicher_variable)
                    + "\n--------------------PID AUTOTUNED VALUES: ------------------------\n"
                )

            # logging.info(self.temp)

            ### # von Marcus fuer ino_temp plotten ##########
            # file = open( '/home/pi/printer_data/config/temp_log_'+ str(datetime.date.today()) + '.csv','a+') # opens or creates file with date in name.open in append mode.
            # file.write( "\n" + str( datetime.datetime.now().time() ) + " " + str(self.temp)  ) #writes time and temp to file
            # file.close()

        return eventtime + SERIAL_TIMER

    def _run_Write(self, eventtime):
        """Write the messages that are in the queue to the serial connection

        :param eventtime: current event time
        :type eventtime: ?
        :return: tell reactor not to call this function any more (if not available)
        :rtype: ?
        """
        # logging.info(f"J: Write queue: status (empty) = {self.write_queue.empty()}")
        # logging.info("Ino run write.")
        while not self.write_queue.empty():
            try:
                text_line = self.write_queue.get_nowait()
            except Empty:
                continue

            if text_line:
                try:
                    # logging.info("Ino run write text_line " + text_line)
                    self.serial.write((text_line + ";\x00").encode())
                    # logging.info("Ino did ran write text_line " + text_line)
                except SerialException:
                    logging.error("Unable to communicate with the Ino. Write")
                    self.signal_disconnect = True
                    return self.reactor.NEVER
        return eventtime + SERIAL_TIMER



    def _get_extruder_for_commands(self,index,gcmd):
        """lookup of the extruder the heater and sensor belong to

        :param index: extruder number
        :type index: int
        :param gcmd: gcode command (object) that is processed
        :type gcmd: ?
        """
        if index is not None:
            section = 'extruder'
            if index:
                section = 'extruder%d' % (index,)
            extruder = self.printer.lookup_object(section, None)
            if extruder is None:
                raise gcmd.error("Extruder not configured.")
        else:
            extruder = self.printer.lookup_object('toolhead').get_extruder()
        return extruder

    def _send_commands_to_extruder_ino(self,heater,message,gcmd):
        """write messages to queue if heater is PLA_INO heater

        :param heater: heater object
        :type heater: ?
        :param message: message that should be put in the queue
        :type message: ?
        :param gcmd: gcode command (object) that is processed
        :type gcmd: ?
        :raises gcmd.error: raises error if command can not be executed on the configured heater
        """
        if heater.__class__.__name__ == "PLA_INO_Heater":
            logging.info("J: sending command to PLA_INO_Heater")
            queue = heater.sensor.write_queue
            logging.info(f"J: queue: {queue}, message: {message}")
            queue.put(message)
        else:
            raise gcmd.error("Command not defined for this heater.")

    cmd_INO_FREQUENCY_help = ""

    def cmd_INO_FREQUENCY(self, gcmd):
        """custom gcode command for changing the INO frequency

        :param gcmd: gcode command (object) that is processed
        :type gcmd: ?
        """
        t = gcmd.get_float("F", 0.0)
        index = gcmd.get_int('T', None, minval=0)
        s = "f " + str(int(t))

        extruder = self._get_extruder_for_commands(index,gcmd)
        heater = extruder.get_heater()

        self._send_commands_to_extruder_ino(heater,s,gcmd)

    cmd_INO_PID_TUNE_help = "z.B.: INO_PID_TUNE PID=250"

    def cmd_INO_PID_TUNE(self, gcmd):
        """custom gcode command for tuning the PID

        :param gcmd: gcode command (object) that is processed
        :type gcmd: ?
        """
        variable = gcmd.get_float("PID", 0.0)
        index = gcmd.get_int('T', None, minval=0)
        s = "pid " + str(float(variable))

        extruder = self._get_extruder_for_commands(index,gcmd)
        heater = extruder.get_heater()

        self._send_commands_to_extruder_ino(heater,s,gcmd)

    cmd_INO_SET_PID_VALUES_help = ""

    def cmd_INO_SET_PID_VALUES(self, gcmd):
        """custom gcode command for setting new PID values

        :param gcmd: gcode command (object) that is processed
        :type gcmd: ?
        """
        index = gcmd.get_int('T', None, minval=0)
        extruder = self._get_extruder_for_commands(index,gcmd)
        heater = extruder.get_heater()

        kp = gcmd.get_float("Kp", 0.0)
        s = "kp " + str(float(kp))
        self._send_commands_to_extruder_ino(heater,s,gcmd)

        ki = gcmd.get_float("Ki", 0.0)
        s = "ki " + str(float(ki))
        self._send_commands_to_extruder_ino(heater,s,gcmd)

        kd = gcmd.get_float("Kd", 0.0)
        s = "kd " + str(float(kd))
        self._send_commands_to_extruder_ino(heater,s,gcmd)

    cmd_INO_RESET_ERROR_FLAGS_help = "resets internel errors in INO"

    def cmd_INO_RESET_ERROR_FLAGS(self, gcmd):
        """custom gcode command for resetting the error flags

        :param gcmd: gcode command (object) that is processed
        :type gcmd: ?
        """
        index = gcmd.get_int('T', None, minval=0)
        s = "q"

        extruder = self._get_extruder_for_commands(index,gcmd)
        heater = extruder.get_heater()

        self._send_commands_to_extruder_ino(heater,s,gcmd)

    cmd_INO_DEBUG_OUT_help = "output one debug line from ino board"

    def cmd_INO_DEBUG_OUT(self, gcmd):
        """custom gcode command for outputting one debug line from the ino board

        :param gcmd: gcode command (object) that is processed
        :type gcmd: ?
        """
        index = gcmd.get_int('T', None, minval=0)
        s = "d 0"

        extruder = self._get_extruder_for_commands(index,gcmd)
        heater = extruder.get_heater()

        self._send_commands_to_extruder_ino(heater,s,gcmd)

    cmd_INO_READ_PID_VALUES_help = "read out internal pid values from ino board"

    def cmd_INO_READ_PID_VALUES(self, gcmd):
        """custom gcode command for reading the current PID values

        :param gcmd: gcode command (object) that is processed
        :type gcmd: ?
        """
        index = gcmd.get_int('T', None, minval=0)
        s = "a"

        extruder = self._get_extruder_for_commands(index,gcmd)
        heater = extruder.get_heater()

        self._send_commands_to_extruder_ino(heater,s,gcmd)


def load_config(config):
    # Register sensor
    pheaters = config.get_printer().load_object(config, "heaters")
    logging.info(f"J: heater in ino sensor: {pheaters.heaters}")
    pheaters.add_sensor_factory("PLA_INO_SENSOR", PLA_INO_Sensor)
