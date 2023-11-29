# Klipper for Ino Trident

![](https://avatars.githubusercontent.com/u/139325225?s=200&v=4)

# Installation and Configuration Guide

This will guide you through the setup of the Ino Trident for Klipper. It will replace your current Klipper Version with ours and can still be updated with the moonraker update manager. 

## Step 1: Update Moonraker Configuration

Edit your `moonraker.cfg` to include the following:

```python
[update_manager]
refresh_interval: 168
enable_auto_refresh: True
enable_repo_debug: True # Add this line
```

## Step 2: Install the Custom Klipper Version

1. Reboot your Raspberry Pi.
2. Execute the following commands to replace your existing Klipper with our version:

```bash
rm -rf ~/klipper
cd ~/ && git clone git@gitlab.com:plasmics/klipper_joey.git
mv klipper_joey klipper
```

3. Run the following command to identify the USB serial port:

```bash
ls /dev/serial/by-id/*
```

Make a note of the USB serial port that looks like this for later use:

> /dev/serial/by-id/usb-STMicroelectronics_INO_Virtual_ComPort_XXXXXXXXXXX-if00

## Step 3: Update Printer Configuration

Open your `printer.cfg` and make the following changes:

```python
[extruder] 
heater_pin: PC12  # Unused pin as placeholder
sensor_type: PLA_INO_SENSOR
heater_type: PLA_INO
control: pid
# Important first PID Values
pid_Kp: 13.41
pid_Ki: 30.91
pid_Kd: 1.46
min_temp: 10
max_temp: 450
serial: /dev/serial/by-id/usb-STMicroelectronics_INO_Virtual_ComPort_XXXXXXXXXXX-if00  # Use the serial name you copied earlier
PLA_INO_report_time: 0.1
```

## Step 4: PID Tune

1. Run the following gcode:

```bash
INO_PID_TUNE PID=250
```

2. Once completed, execute:

```bash
INO_READ_PID_VALUES
```

Replace the old PID values in the `printer.cfg` [extruder] section with the new ones.


## Step X: Repo specific changes

In order to be able to use the INO heater + the INO Sensor, the config section for the extruder has to have the fields/values
```python
sensor_type: PLA_INO_SENSOR
heater_type: PLA_INO
```

If 'PLA_INO' is given as a heater but 'PLA_INO_SENSOR' is not chosen as the sensor, an error will be thrown.
If there is another value in 'heater_type' or no such field at all, the standard heater class will be initialized instead (this reflects the state where another hotend is being used).
The entire implementation circling around the INO can be found in the files 'klippy/extras/heaters.py' for the heating part (the class "PLA_INO_Heater" was introduced) and the file 'klippy/extras/pla_ino_sensor.py' where the serial connection to the INO is handled.

If you want to add multiple extruders, just do it the same way as you would always do it (call the section [extruderx] for extruder number 'x'), but don't forget to add the sensor and heater type!

To read out the currently processed Gcode line, an additional module "klippy/extras/gcode_tracker.py' was added. This introduces a simple printer-object with the only task of collecting information about the current gcode line and the respective number of gcode commands processed so far.
To initialize the object, make sure to add the following to you printer.cfg file

```python
[gcode_tracker printer]
```
(The 'printer' part makes absolutely no sense, but without adding it (or something different instead) Klipper gets mad) 

In order to access the information collected by this module, one can call it the following way:

```python
{"id": 123, "method": "objects/query", "params": {"objects": {"gcode_tracker printer": null}}}\x03
```

which gives as a response something like the following

```python
{"id":123,"result":{"eventtime":2878.525718728,"status":{"gcode_tracker printer":{"current_gcode_line":"G104 T0 S200","current_gcode_line_count":5}}}}
```

For more information on this, check out the following ressource: https://www.klipper3d.org/API_Server.html

There is also a new file 'klippy/extras/talk_to_klipper.py' that opens a connection to the klipper socket and allows to send messages (and receive the answer) - so check this out if you want to play around with the socket - e.g., to test the above query.

## MCU error
One error I encountered so far was the 'MCU shutdown'. I have no idea where it came from and I wasn't able to reproduce it, but IF it happens, try the following:

- open the printer.cfg file
- change the serial of your MCU

```python
[mcu]
serial: /dev/serial/by-id/usb-Klipper_stm32g0b1xx_m8p-if00
restart_method: command
```
   by removing the last character (and memorize it!)

- restart the entire thing (try 'Rollover Logs->Klipper Logs' (this reloads any python code changes), 'Restart', 'Firmware Restart', 'Reboot' in this order for maximum efficiency) - at some point the error should be gone but instead you will see a note (blue box) instead of your (red or yellow) error message

- now change the printer.cfg back to the original thing 

- restart again and - Voilá, it works! (hopefully)