DROP DATABASE IF EXISTS scrap_e;
CREATE DATABASE scrap_e;
USE scrap_e;

CREATE TABLE devices (
    device_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(255),
    device_type ENUM('sensor', 'actuator') NOT NULL,
    unit VARCHAR(20),

    UNIQUE KEY uq_device_name (name),
    INDEX idx_device_type (device_type)
);

CREATE TABLE actions (
    action_id INT AUTO_INCREMENT PRIMARY KEY,
    action_name VARCHAR(100) NOT NULL,
    action_description VARCHAR(255),

    UNIQUE KEY uq_action_name (action_name)
);


CREATE TABLE history (
    history_id INT AUTO_INCREMENT PRIMARY KEY,
    device_id INT NOT NULL,
    action_id INT NULL,

    history_type ENUM('measurement', 'action') NOT NULL,

    value_number DOUBLE NULL,
    value_text VARCHAR(100) NULL,

    comment VARCHAR(255),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_history_device
        FOREIGN KEY (device_id)
        REFERENCES devices(device_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    CONSTRAINT fk_history_action
        FOREIGN KEY (action_id)
        REFERENCES actions(action_id)
        ON DELETE SET NULL
        ON UPDATE CASCADE,

    INDEX idx_history_created_at (created_at),
    INDEX idx_history_device_id (device_id),
    INDEX idx_history_type (history_type)
);

INSERT INTO devices
(name, description, device_type, unit)
VALUES
('DHT11 Temperature', 'Temperature from the DHT11 sensor', 'sensor', '°C'),
('DHT11 Humidity', 'Humidity from the DHT11 sensor', 'sensor', '%'),
('VL53L1X Distance', 'Distance measured by the time-of-flight sensor', 'sensor', 'mm'),
('CO2 Sensor', 'CO2 value measured by the PWM CO2 sensor', 'sensor', 'ppm'),
('Battery 1 Voltage', 'Voltage of battery input 1', 'sensor', 'V'),
('Battery 2 Voltage', 'Voltage of battery input 2', 'sensor', 'V'),
('LDR Left', 'Light intensity from left LDR on MCP3008 channel 3', 'sensor', 'raw'),
('LDR Right', 'Light intensity from right LDR on MCP3008 channel 4', 'sensor', 'raw'),
('GPS Latitude', 'Latitude from the GPS module', 'sensor', 'deg'),
('GPS Longitude', 'Longitude from the GPS module', 'sensor', 'deg'),

('Drive Left Motor', 'Left drive motor for the tracks', 'actuator', 'state'),
('Drive Right Motor', 'Right drive motor for the tracks', 'actuator', 'state'),
('Neck Tilt Servo', 'Servo that tilts Scrap-E his head up and down', 'actuator', 'µs'),
('Neck Rotation Servo', 'Servo that rotates Scrap-E his head left and right', 'actuator', 'µs'),
('Left Eyebrow Servo', 'Servo for the left eyebrow expression', 'actuator', 'µs'),
('Right Eyebrow Servo', 'Servo for the right eyebrow expression', 'actuator', 'µs'),
('Chest Hatch Servo', 'Servo that opens and closes the front hatch', 'actuator', 'µs'),
('Arm Servo', 'Servo used for Scrap-E his arm movement', 'actuator', 'µs');

INSERT INTO actions
(action_name, action_description)
VALUES
('measure', 'A sensor value was measured'),

('move_forward', 'Scrap-E starts moving forward'),
('move_backward', 'Scrap-E starts moving backward'),
('turn_left', 'Scrap-E turns left'),
('turn_right', 'Scrap-E turns right'),
('stop', 'Scrap-E stops moving'),

('servo_move', 'A servo moved to a new pulse width'),

('animation_neutral', 'Scrap-E goes to neutral expression'),
('animation_happy', 'Scrap-E performs happy expression'),
('animation_sad', 'Scrap-E performs sad expression'),
('animation_surprised', 'Scrap-E performs surprised expression'),

('open_hatch', 'The chest hatch opens'),
('close_hatch', 'The chest hatch closes');