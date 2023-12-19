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


## Step 5: Repo specific changes

In order to be able to use the INO heater + the INO Sensor, the config section for the extruder has to have the fields/values
```python
sensor_type: PLA_INO_SENSOR
heater_type: PLA_INO
```

If 'PLA_INO' is given as a heater but 'PLA_INO_SENSOR' is not chosen as the sensor, an error will be thrown.
If there is another value in 'heater_type' or no such field at all, the standard heater class will be initialized instead (this reflects the state where another hotend is being used).
The entire implementation circling around the INO can be found in the files 'klippy/extras/pla_ino_heater.py' for the heating part (the class "PLA_INO_Heater" was introduced) and the file 'klippy/extras/pla_ino_sensor.py' where the serial connection to the INO is handled.

If you want to add multiple extruders, just do it the same way as you would always do it (call the section [extruderx] for extruder number 'x'), but don't forget to add the sensor and heater type!