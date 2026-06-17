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

// =========================================================
// Bat Graph
// =========================================================
let batteryChart = null;

const renderBatteryChart = (battery1Rows, battery2Rows) => {
    const canvas = document.querySelector('#batteryChart');

    if (!canvas) return;

    const battery1 = [...battery1Rows].reverse();
    const battery2 = [...battery2Rows].reverse();

    const amount = Math.min(battery1.length, battery2.length);

    const labels = [];
    const battery1Data = [];
    const battery2Data = [];

    for (let index = 0; index < amount; index++) {
        labels.push(formatTime(battery1[index].created_at));
        battery1Data.push(Number(battery1[index].value_number));
        battery2Data.push(Number(battery2[index].value_number));
    }

    if (batteryChart) {
        batteryChart.data.labels = labels;
        batteryChart.data.datasets[0].data = battery1Data;
        batteryChart.data.datasets[1].data = battery2Data;
        batteryChart.update();
        return;
    }

    batteryChart = new Chart(canvas, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Electronics Battery V',
                    data: battery1Data,

                    borderColor: '#f6b11a',
                    backgroundColor: 'rgba(246, 177, 26, 0.15)',
                    tension: 0.25,
                },
                {
                    label: 'Motors Battery V',
                    data: battery2Data,

                    borderColor: '#DB182E',
                    backgroundColor: 'rgba(219, 24, 46, 0.15)',
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
                y: {
                    min: 2.8,
                    max: 4.3,

                    title: {
                        display: true,
                        text: 'Battery Voltage',
                    },

                    ticks: {
                        callback: function (value) {
                            return value.toFixed(1) + ' V';
                        },
                    },
                },
            },
        },
    });
};


const renderBatteryData = (jsonObject) => {
    const battery1Rows = jsonObject.battery_1 ?? [];
    const battery2Rows = jsonObject.battery_2 ?? [];

    renderBatteryChart(battery1Rows, battery2Rows);
};


// const loadBatteryGraph = async () => {
//     const json = await getAPI('/batteries?limit=25');

//     if (json) {
//         renderBatteryData(json);
//     }
// };

const loadSensorsPage = async () => {
    const dhtJson = await getAPI('/dht11?limit=20');

    if (dhtJson) {
        renderDht11Data(dhtJson);
    }

    const batteryJson = await getAPI('/batteries?limit=25');

    if (batteryJson) {
        renderBatteryData(batteryJson);
    }

    const co2Json = await getAPI('/co2?limit=30');

    if (co2Json) {
        renderCo2Data(co2Json);
    }

    const gpsJson = await getAPI('/gps?limit=10');

    if (gpsJson) {
        renderGpsData(gpsJson);
    }
    const ldrJson = await getAPI('/ldr?limit=25');

    if (ldrJson) {
        renderLdrData(ldrJson);
    }
};

// =========================================================
// CO2 SENSOR GRAPH
// =========================================================

let co2Chart = null;

const renderCo2Chart = (co2Rows) => {
    const canvas = document.querySelector('#co2Chart');

    if (!canvas) return;

    const co2Values = [...co2Rows].reverse();

    const labels = [];
    const co2Data = [];

    for (let index = 0; index < co2Values.length; index++) {
        labels.push(formatTime(co2Values[index].created_at));
        co2Data.push(Number(co2Values[index].value_number));
    }

    if (co2Chart) {
        co2Chart.data.labels = labels;
        co2Chart.data.datasets[0].data = co2Data;
        co2Chart.update();
        return;
    }

    co2Chart = new Chart(canvas, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'CO2 ppm',
                    data: co2Data,

                    borderColor: '#333333',
                    backgroundColor: 'rgba(51, 51, 51, 0.15)',
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
                y: {
                    min: 0,
                    max: 2000,

                    title: {
                        display: true,
                        text: 'CO2 ppm',
                        color: '#333333',
                    },

                    ticks: {
                        color: '#333333',
                    },
                },
            },
        },
    });
};

const renderCo2Data = (jsonObject) => {
    const co2Rows = jsonObject.co2 ?? [];

    updateCo2QualityBox(co2Rows);
    renderCo2Chart(co2Rows);
};


const loadCo2Graph = async () => {
    const json = await getAPI('/co2?limit=30');

    if (json) {
        renderCo2Data(json);
    }
};
// =========================================================
// CO2 AIR QUALITY BOX
// =========================================================

const getCo2QualityInfo = (ppm) => {
    if (ppm === null || ppm === undefined || isNaN(ppm)) {
        return {
            text: 'Waiting for CO2 data...',
            className: 'co2-quality-box--unknown',
        };
    }

    if (ppm <= 600) {
        return {
            text: 'Great Air Quality',
            className: 'co2-quality-box--great',
        };
    }

    if (ppm <= 1000) {
        return {
            text: 'Good Air Quality',
            className: 'co2-quality-box--good',
        };
    }

    if (ppm <= 1400) {
        return {
            text: 'Okay Air Quality',
            className: 'co2-quality-box--okay',
        };
    }

    if (ppm <= 1800) {
        return {
            text: 'Poor Air Quality',
            className: 'co2-quality-box--poor',
        };
    }

    return {
        text: 'Very Bad Air Quality',
        className: 'co2-quality-box--bad',
    };
};


const updateCo2QualityBox = (co2Rows) => {
    const qualityBox = document.querySelector('.js-co2-quality-box');

    if (!qualityBox) return;

    const latestRow = co2Rows[0];
    const ppm = latestRow ? Number(latestRow.value_number) : null;
    const qualityInfo = getCo2QualityInfo(ppm);

    qualityBox.classList.remove(
        'co2-quality-box--unknown',
        'co2-quality-box--great',
        'co2-quality-box--good',
        'co2-quality-box--okay',
        'co2-quality-box--poor',
        'co2-quality-box--bad'
    );

    qualityBox.classList.add(qualityInfo.className);

    if (ppm === null || isNaN(ppm)) {
        qualityBox.textContent = qualityInfo.text;
        return;
    }

    qualityBox.innerHTML = `
    <strong>${qualityInfo.text}</strong>
    <span>${ppm.toFixed(0)} ppm</span>
  `;
};
// =========================================================
// LDR SENSOR GRAPH
// =========================================================

let ldrChart = null;

const renderLdrChart = (ldr1Rows, ldr2Rows) => {
    const canvas = document.querySelector('#ldrChart');

    if (!canvas) return;

    const ldr1 = [...ldr1Rows].reverse();
    const ldr2 = [...ldr2Rows].reverse();

    const amount = Math.min(ldr1.length, ldr2.length);

    const labels = [];
    const ldr1Data = [];
    const ldr2Data = [];

    for (let index = 0; index < amount; index++) {
        labels.push(formatTime(ldr1[index].created_at));
        ldr1Data.push(Number(ldr1[index].value_number));
        ldr2Data.push(Number(ldr2[index].value_number));
    }

    if (ldrChart) {
        ldrChart.data.labels = labels;
        ldrChart.data.datasets[0].data = ldr1Data;
        ldrChart.data.datasets[1].data = ldr2Data;
        ldrChart.update();
        return;
    }

    ldrChart = new Chart(canvas, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'LDR 1 lux',
                    data: ldr1Data,

                    borderColor: '#f6b11a',
                    backgroundColor: 'rgba(246, 177, 26, 0.15)',
                    tension: 0.25,
                },
                {
                    label: 'LDR 2 lux',
                    data: ldr2Data,

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
                y: {
                    beginAtZero: true,

                    title: {
                        display: true,
                        text: 'Light intensity lux',
                    },

                    ticks: {
                        callback: function (value) {
                            return value + ' lux';
                        },
                    },
                },
            },
        },
    });
};


const renderLdrData = (jsonObject) => {
    const ldr1Rows = jsonObject.ldr_1 ?? [];
    const ldr2Rows = jsonObject.ldr_2 ?? [];

    renderLdrChart(ldr1Rows, ldr2Rows);
};


const loadLdrGraph = async () => {
    const json = await getAPI('/ldr?limit=25');

    if (json) {
        renderLdrData(json);
    }
};

// =========================================================
// GPS TABLE
// =========================================================

const renderGpsTable = (latitudeRows, longitudeRows) => {
    const tableBody = document.querySelector('.js-gps-table');

    if (!tableBody) return;

    const amount = Math.min(latitudeRows.length, longitudeRows.length);

    let html = '';

    for (let index = 0; index < amount; index++) {
        const latitudeRow = latitudeRows[index];
        const longitudeRow = longitudeRows[index];

        const time = formatTime(latitudeRow.created_at);
        const latitude = Number(latitudeRow.value_number).toFixed(6);
        const longitude = Number(longitudeRow.value_number).toFixed(6);

        html += `
      <tr>
        <td>${time}</td>
        <td>${latitude}</td>
        <td>${longitude}</td>
      </tr>
    `;
    }

    if (html === '') {
        html = `
      <tr>
        <td colspan="3">Waiting for GPS data...</td>
      </tr>
    `;
    }

    tableBody.innerHTML = html;
};


const renderGpsData = (jsonObject) => {
    const latitudeRows = jsonObject.latitude ?? [];
    const longitudeRows = jsonObject.longitude ?? [];

    renderGpsTable(latitudeRows, longitudeRows);
};


const loadGpsTable = async () => {
    const json = await getAPI('/gps?limit=10');

    if (json) {
        renderGpsData(json);
    }
};

// =========================================================
// HOME PAGE RENDER
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
    socketio.on('B2F_battery_data', (jsonObject) => {
        console.log('Battery graph data received:', jsonObject);

        if (currentPage === 'sensors') {
            renderBatteryData(jsonObject);
        }
    });

    socketio.on('B2F_co2_data', (jsonObject) => {
        console.log('CO2 data received:', jsonObject);

        if (currentPage === 'sensors') {
            renderCo2Data(jsonObject);
        }
    });

    socketio.on('B2F_gps_data', (jsonObject) => {
        console.log('GPS data received:', jsonObject);

        if (currentPage === 'sensors') {
            renderGpsData(jsonObject);
        }
    });
    socketio.on('B2F_ldr_data', (jsonObject) => {
        console.log('LDR data received:', jsonObject);

        if (currentPage === 'sensors') {
            renderLdrData(jsonObject);
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