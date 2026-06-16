'use strict';

// =========================================================
// SCRAP-E JS
// For now: index.html battery display
// =========================================================

const lanIP = 'http://192.168.168.169:8000';
const socketio = io(lanIP);

const currentPage = document.body.dataset.page;


// =========================================================
// BATTERY SETTINGS
// =========================================================

const BATTERY_FULL_VOLTAGE = 4.2;
const BATTERY_EMPTY_VOLTAGE = 3.0;
const BATTERY_DANGER_VOLTAGE = 2.9;


// =========================================================
// API HELPER
// =========================================================

const getAPI = async (endpoint) => {
    const url = `${lanIP}/api/v1${endpoint}`;

    try {
        const response = await fetch(url);

        if (!response.ok) {
            console.error(`GET failed: ${url}`);
            return null;
        }

        return await response.json();
    } catch (error) {
        console.error('Backend connection error:', error);
        return null;
    }
};


// =========================================================
// BATTERY FUNCTIONS
// =========================================================

const calculateBatterySegments = (voltage) => {
    if (voltage === null || voltage === undefined || isNaN(voltage)) {
        return 0;
    }

    // At 3.0V, only the bottom segment is on.
    if (voltage <= BATTERY_EMPTY_VOLTAGE) {
        return 1;
    }

    // At 4.2V, all 10 segments are on.
    if (voltage >= BATTERY_FULL_VOLTAGE) {
        return 10;
    }

    // From 3.0V to 4.2V, fill the other 9 segments.
    const percentage = (voltage - BATTERY_EMPTY_VOLTAGE) / (BATTERY_FULL_VOLTAGE - BATTERY_EMPTY_VOLTAGE);
    const extraSegments = Math.ceil(percentage * 9);

    return 1 + extraSegments;
};


const updateBatteryDisplay = (batteryNumber, voltage) => {
    const battery = document.querySelector(`.js-battery-display[data-battery="${batteryNumber}"]`);

    if (!battery) return;

    const segments = battery.querySelectorAll('.battery-segment');
    const activeSegments = calculateBatterySegments(voltage);
    const isDanger = voltage <= BATTERY_DANGER_VOLTAGE;

    segments.forEach((segment, index) => {
        // index 0 is the top segment.
        // So we count from the bottom instead.
        const fromBottom = segments.length - index;

        segment.classList.remove('battery-segment--active');
        segment.classList.remove('battery-segment--danger');

        if (fromBottom <= activeSegments) {
            if (isDanger) {
                segment.classList.add('battery-segment--danger');
            } else {
                segment.classList.add('battery-segment--active');
            }
        }
    });
};


const updateBatteryVoltageText = (batteryNumber, voltage) => {
    const element = document.querySelector(`.js-battery-${batteryNumber}-voltage`);

    if (!element) return;

    if (voltage === null || voltage === undefined || isNaN(voltage)) {
        element.textContent = '--';
        return;
    }

    element.textContent = voltage.toFixed(2);
};

// =========================================================
// DHT11 SENSOR PAGE
// =========================================================

let dht11Chart = null;

const formatTime = (dateString) => {
    if (!dateString) return '--';

    const date = new Date(dateString);

    return date.toLocaleTimeString('en-GB', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
    });
};

const renderDht11Chart = (temperatureRows, humidityRows) => {
    const canvas = document.querySelector('#dht11Chart');

    if (!canvas) return;

    const temperatures = [...temperatureRows].reverse();
    const humidities = [...humidityRows].reverse();

    const amount = Math.min(temperatures.length, humidities.length);

    const labels = [];
    const temperatureData = [];
    const humidityData = [];

    for (let index = 0; index < amount; index++) {
        labels.push(formatTime(temperatures[index].created_at));
        temperatureData.push(Number(temperatures[index].value_number));
        humidityData.push(Number(humidities[index].value_number));
    }

    if (dht11Chart) {
        dht11Chart.data.labels = labels;
        dht11Chart.data.datasets[0].data = temperatureData;
        dht11Chart.data.datasets[1].data = humidityData;
        dht11Chart.update();
        return;
    }

    dht11Chart = new Chart(canvas, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Temperature °C',
                    data: temperatureData,
                    yAxisID: 'temperatureAxis',

                    borderColor: '#DB182E',
                    backgroundColor: 'rgba(219, 24, 46, 0.15)',
                    tension: 0.25,
                },
                {
                    label: 'Humidity %',
                    data: humidityData,
                    yAxisID: 'humidityAxis',

                    borderColor: '#35538B',
                    backgroundColor: 'rgba(53, 83, 139, 0.15)',
                    tension: 0.25,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,

            interaction: {
                mode: 'index',
                intersect: false,
            },

            scales: {
                temperatureAxis: {
                    type: 'linear',
                    position: 'left',
                    min: 0,
                    max: 45,

                    title: {
                        display: true,
                        text: 'Temperature °C',
                        color: '#DB182E',
                    },

                    ticks: {
                        color: '#DB182E',
                    },
                },

                humidityAxis: {
                    type: 'linear',
                    position: 'right',
                    min: 0,
                    max: 100,

                    title: {
                        display: true,
                        text: 'Humidity %',
                        color: '#35538B',
                    },

                    ticks: {
                        color: '#35538B',
                    },

                    grid: {
                        drawOnChartArea: false,
                    },
                },
            },
        },
    });
};


const renderDht11Data = (jsonObject) => {
    const temperatureRows = jsonObject.temperature ?? [];
    const humidityRows = jsonObject.humidity ?? [];

    renderDht11Chart(temperatureRows, humidityRows);
};


const loadSensorsPage = async () => {
    const json = await getAPI('/dht11?limit=20');

    if (json) {
        renderDht11Data(json);
    }
};

// =========================================================
// HOME PAGE RENDER
// This is the function you were missing.
// It looks for the latest Battery 1 and Battery 2 values.
// =========================================================

const renderHomeLatestMeasurements = (measurements) => {
    if (!measurements || measurements.length === 0) return;

    const latestBattery1 = measurements.find((row) => row.device_name === 'Battery 1 Voltage');
    const latestBattery2 = measurements.find((row) => row.device_name === 'Battery 2 Voltage');

    if (latestBattery1) {
        const voltage = Number(latestBattery1.value_number);

        updateBatteryVoltageText(1, voltage);
        updateBatteryDisplay(1, voltage);
    }

    if (latestBattery2) {
        const voltage = Number(latestBattery2.value_number);

        updateBatteryVoltageText(2, voltage);
        updateBatteryDisplay(2, voltage);
    }
};


// =========================================================
// HOME PAGE LOAD
// Loads existing database values when the page opens.
// =========================================================

const loadHomePage = async () => {
    const json = await getAPI('/measurements?limit=50');

    if (json) {
        renderHomeLatestMeasurements(json.measurements);
    }
};


// =========================================================
// SOCKET.IO
// Updates the battery display live when backend saves new data.
// =========================================================

const listenToSocket = () => {
    socketio.on('connect', () => {
        console.log('Connected to Scrap-E backend');
    });

    socketio.on('disconnect', () => {
        console.log('Disconnected from Scrap-E backend');
    });

    socketio.on('B2F_dashboard_data', (jsonObject) => {
        console.log('Dashboard data received:', jsonObject);

        if (currentPage === 'home') {
            renderHomeLatestMeasurements(jsonObject.measurements);
        }
    });

    socketio.on('B2F_new_measurement', (jsonObject) => {
        console.log('New measurement received:', jsonObject);

        if (currentPage === 'home') {
            renderHomeLatestMeasurements(jsonObject.measurements);
        }
    });

    socketio.on('B2F_dht11_data', (jsonObject) => {
        console.log('DHT11 data received:', jsonObject);

        if (currentPage === 'sensors') {
            renderDht11Data(jsonObject);
        }
    });
};

// =========================================================
// HAMBURGER MENU
// =========================================================

const setupMobileMenu = () => {
    const menuButton = document.querySelector('.js-menu-button');
    const closeButton = document.querySelector('.js-menu-close');
    const mobileMenu = document.querySelector('.js-mobile-menu');

    if (!menuButton || !closeButton || !mobileMenu) return;

    menuButton.addEventListener('click', () => {
        mobileMenu.classList.add('mobile-menu--open');
        document.body.classList.add('menu-open');
    });

    closeButton.addEventListener('click', () => {
        mobileMenu.classList.remove('mobile-menu--open');
        document.body.classList.remove('menu-open');
    });
};

// =========================================================
// INIT
// =========================================================

const init = () => {
    console.info(`Scrap-E frontend loaded: ${currentPage}`);

    setupMobileMenu();
    listenToSocket();

    if (currentPage === 'home') {
        loadHomePage();
    }

    if (currentPage === 'sensors') {
        loadSensorsPage();
    }
};

document.addEventListener('DOMContentLoaded', init);