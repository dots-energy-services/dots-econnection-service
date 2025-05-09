from dataclasses import dataclass
from datetime import datetime
from typing import List
import unittest

import esdl
from EConnectionService.EConnection import CalculationServiceEConnection
from dots_infrastructure.DataClasses import SimulatorConfiguration, TimeStepInformation
from dots_infrastructure.test_infra.InfluxDBMock import InfluxDBMock
import helics as h
from esdl.esdl_handler import EnergySystemHandler

from dots_infrastructure import CalculationServiceHelperFunctions


BROKER_TEST_PORT = 23404
START_DATE_TIME = datetime(2024, 1, 1, 0, 0, 0)
SIMULATION_DURATION_IN_SECONDS = 960

def simulator_environment_e_connection():
    return SimulatorConfiguration("EConnection", ["5c19dcff-b004-4644-99b9-f42d15a34f3a", "1412f71f-a9d2-4c66-a834-385cf91c3767"], "Mock-Econnection", "127.0.0.1", BROKER_TEST_PORT, "test-id", SIMULATION_DURATION_IN_SECONDS, START_DATE_TIME, "test-host", "test-port", "test-username", "test-password", "test-database-name", h.HelicsLogLevel.TRACE, ["PVInstallation", "EVChargingStation","EConnection"])

@dataclass
class EmsTestParam:
    esdl_id : str
    expected_outcomes : List[str]
    esdl_file : str

class Test(unittest.TestCase):

    def load_esdl_file(self, file_path):
        esh = EnergySystemHandler()
        esh.load_file(file_path)
        return esh.get_energy_system()
    
    def init_e_connection_service(self, energy_system : esdl.EnergySystem):
        service = CalculationServiceEConnection()
        service.influx_connector = InfluxDBMock()
        service.init_calculation_service(energy_system)
        return service

    def setUp(self):
        CalculationServiceHelperFunctions.get_simulator_configuration_from_environment = simulator_environment_e_connection

    def test_different_tariff_instruments(self):
        test_examples = [
            EmsTestParam("5c19dcff-b004-4644-99b9-f42d15a34f3a", ["dispatch_pv", "dispatch_ev", "heat_power_to_tank_dhw", "heat_power_to_buffer", "heat_power_to_dhw", "heat_power_to_house", "aggregated_active_power", "aggregated_reactive_power"], 'test-bandwidth.esdl'),
            EmsTestParam("1412f71f-a9d2-4c66-a834-385cf91c3767", ["aggregated_active_power", "aggregated_reactive_power", "dispatch_pv", "heat_power_to_buffer_hhp", "heat_power_to_house_hhp"], 'test-bandwidth.esdl'),
            EmsTestParam("5c19dcff-b004-4644-99b9-f42d15a34f3a", ["dispatch_pv", "dispatch_ev", "heat_power_to_tank_dhw", "heat_power_to_buffer", "heat_power_to_dhw", "heat_power_to_house", "aggregated_active_power", "aggregated_reactive_power"], 'test-variable-peak-tariff.esdl'),
            EmsTestParam("1412f71f-a9d2-4c66-a834-385cf91c3767", ["aggregated_active_power", "aggregated_reactive_power", "dispatch_pv", "heat_power_to_buffer_hhp", "heat_power_to_house_hhp"], 'test-variable-peak-tariff.esdl'),
            EmsTestParam("5c19dcff-b004-4644-99b9-f42d15a34f3a", ["dispatch_pv", "dispatch_ev", "heat_power_to_tank_dhw", "heat_power_to_buffer", "heat_power_to_dhw", "heat_power_to_house", "aggregated_active_power", "aggregated_reactive_power"], 'test-peak-tariff.esdl'),
            EmsTestParam("1412f71f-a9d2-4c66-a834-385cf91c3767", ["aggregated_active_power", "aggregated_reactive_power", "dispatch_pv", "heat_power_to_buffer_hhp", "heat_power_to_house_hhp"], 'test-peak-tariff.esdl')
        ]

        for i in range(0, len(test_examples)):
            with self.subTest(i=i, params = test_examples[i]):

                test_param = test_examples[i]
                energy_system = self.load_esdl_file(test_param.esdl_file)
                service = self.init_e_connection_service(energy_system)

                edemand_param = {}
                edemand_param['prices_next_day'] = [0.04102, 0.0451, 0.0451, 0.0451, 0.0451, 0.0549, 0.0549, 0.0549, 0.0549, 0.07715000000000001, 0.07715000000000001, 0.07715000000000001, 0.07715000000000001, 0.1001, 0.1001, 0.1001, 0.1001, 0.09673000000000001, 0.09673000000000001, 0.09673000000000001, 0.09673000000000001, 0.0992, 0.0992, 0.0992, 0.0992, 0.10497, 0.10497, 0.10497, 0.10497, 0.09386, 0.09386, 0.09386, 0.09386, 0.09384999999999999, 0.09384999999999999, 0.09384999999999999, 0.09384999999999999, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.13426, 0.13426, 0.13426]

                # Electricity demand
                edemand_param['active_power'] = [52.0, 48.0, 152.0, 55.9999999999999, 48.0, 52.0, 444.0, 284.0, 327.9999999999999, 348.0, 316.0, 572.0000000000001, 276.0, 272.0, 272.0, 272.0, 100.0, 72.0, 72.0, 72.0, 68.0, 72.0, 68.0, 76.0, 72.0, 68.0, 72.0, 72.0, 68.0, 92.0, 148.0, 140.0, 140.0, 136.0, 132.0, 132.0, 163.9999999999999, 288.0, 360.0, 387.9999999999999, 384.0, 392.0, 387.9999999999999, 436.0, 392.0, 387.9999999999999, 468.0, 452.0]
                edemand_param['reactive_power'] = [17.091573469300883, 15.776837048585431, 49.9599839871872, 18.406309890016303, 15.776837048585431, 17.091573469300883, 145.93574269941524, 93.34628587079713, 107.80838649866708, 114.38206860224437, 103.86417723652076, 188.00730816230976, 90.71681302936624, 89.40207660865077, 89.40207660865077, 89.40207660865077, 32.86841051788632, 23.665255572878145, 23.665255572878145, 23.665255572878145, 22.350519152162693, 23.665255572878145, 22.350519152162693, 24.9799919935936, 23.665255572878145, 22.350519152162693, 23.665255572878145, 23.665255572878145, 22.350519152162693, 30.23893767645541, 48.645247566471745, 46.01577472504084, 46.01577472504084, 44.70103830432539, 43.38630188360994, 43.38630188360994, 53.90419324933352, 94.66102229151258, 118.32627786439073, 127.52943280939887, 126.21469638868345, 128.84416923011435, 127.52943280939887, 143.30626985798435, 128.84416923011435, 127.52943280939887, 153.82416122370796, 148.56521554084614]

                # EV
                edemand_param['state_of_charge_ev'] = 244800000.0

                # Weather
                edemand_param["solar_irradiance"] = [152.77777777777777, 170.13888888888889, 187.5, 204.86111111111111, 222.22222222222223, 227.7777777777778, 233.3333333333333, 238.8888888888889, 244.44444444444449, 247.22222222222223, 250.0, 252.7777777777778, 255.5555555555556, 241.66666666666669, 227.7777777777778, 213.88888888888889, 200.0, 180.5555555555556, 161.11111111111111, 141.66666666666669, 122.22222222222224, 97.91666666666669, 73.61111111111111, 49.30555555555557, 25.0, 18.75, 12.5, 6.250000000000001, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
                edemand_param["air_temperature"] = [279.25, 279.54999999999995, 279.85, 280.15, 280.45, 280.7, 280.95, 281.2, 281.45, 281.775, 282.1, 282.42499999999995, 282.75, 282.85, 282.95, 283.04999999999995, 283.15, 283.15, 283.15, 283.15, 283.15, 282.95, 282.75, 282.54999999999995, 282.35, 282.275, 282.2, 282.125, 282.04999999999995, 282.125, 282.2, 282.275, 282.35, 282.375, 282.4, 282.42499999999995, 282.45, 282.375, 282.29999999999995, 282.225, 282.15, 282.025, 281.9, 281.775, 281.65, 281.625, 281.6, 281.575]
                edemand_param["soil_temperature"] = [281.3833333333333, 281.37916666666666, 281.375, 281.37083333333334, 281.3666666666666, 281.36249999999995, 281.3583333333333, 281.35416666666663, 281.35, 281.3458333333333, 281.34166666666664, 281.3375, 281.3333333333333, 281.32916666666665, 281.325, 281.3208333333333, 281.31666666666666, 281.3125, 281.30833333333334, 281.3041666666666, 281.29999999999995, 281.2958333333333, 281.29166666666663, 281.2875, 281.2833333333333, 281.27916666666664, 281.275, 281.2708333333333, 281.26666666666665, 281.2625, 281.2583333333333, 281.25416666666666, 281.25, 281.24583333333334, 281.2416666666666, 281.23749999999995, 281.2333333333333, 281.22916666666663, 281.225, 281.2208333333333, 281.21666666666664, 281.2125, 281.2083333333333, 281.20416666666665, 281.2, 281.1958333333333, 281.19166666666666, 281.1875]
                
                # PV
                edemand_param["potential_active_power"] = [977.7777777777778, 1088.888888888889, 1200.0, 1311.1111111111113, 1422.2222222222224, 1457.777777777778, 1493.333333333333, 1528.8888888888891, 1564.4444444444448, 1582.2222222222224, 1600.0, 1617.777777777778, 1635.5555555555559, 1546.666666666667, 1457.777777777778, 1368.888888888889, 1280.0, 1155.5555555555559, 1031.111111111111, 906.6666666666669, 782.2222222222224, 626.6666666666669, 471.11111111111114, 315.55555555555566, 160.0, 120.0, 80.0, 40.00000000000001, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
                
                # heatpump
                edemand_param["dhw_temperature"] = 328.1499987884123
                edemand_param["buffer_temperature"] = 319.72477588114043
                edemand_param["house_temperatures"] = [291.85009999999994, 288.3497627218783]


                # Execute
                ret_val = service.calculate_dispatch(edemand_param, datetime(2020,1,14), TimeStepInformation(24,24), test_param.esdl_id, energy_system)

                for expected_outcome in test_param.expected_outcomes:
                    self.assertIn(expected_outcome, ret_val.keys())

    def test_without_ems(self):
        energy_system = self.load_esdl_file('test-without-ems.esdl')
        service = self.init_e_connection_service(energy_system)

         # Electricity demand
        edemand_param= {}
        edemand_param['active_power'] = [104.0, 60.0, 24.0, 24.0, 27.9999999999999, 36.0, 24.0, 108.0, 72.0, 27.9999999999999, 24.0, 27.9999999999999, 27.9999999999999, 27.9999999999999, 104.0, 76.0, 24.0, 24.0, 27.9999999999999, 24.0, 24.0, 72.0, 104.0, 36.0, 24.0, 24.0, 27.9999999999999, 24.0, 32.0, 104.0, 68.0, 48.0, 55.9999999999999, 53.916666666666565, 47.83333333333333, 61.75, 119.66666666666666, 64.72222222222223, 21.77777777777778, 18.833333333333336, 7.888888888888893, -0.44444444444444287, -4.777777777777779, 30.888888888888893, 54.55555555555556, 239.94444444444446, -18.666666666666657, -21.277777777777786]
        edemand_param['reactive_power'] =  [34.183146938601766, 19.72104631073179, 7.888418524292716, 7.888418524292716, 9.203154945008135, 11.832627786439073, 7.888418524292716, 35.49788335931722, 23.665255572878145, 9.203154945008135, 7.888418524292716, 9.203154945008135, 9.203154945008135, 9.203154945008135, 34.183146938601766, 24.9799919935936, 7.888418524292716, 7.888418524292716, 9.203154945008135, 7.888418524292716, 7.888418524292716, 23.665255572878145, 34.183146938601766, 11.832627786439073, 7.888418524292716, 7.888418524292716, 9.203154945008135, 7.888418524292716, 10.51789136572362, 34.183146938601766, 22.350519152162693, 15.776837048585431, 18.406309890016303, 17.72155133756034, 15.722056364388953, 20.2962434947948, 39.33253125307062, 21.273165696298644, 7.15800940167302, 6.190217314201924, 2.5929523852999217, -0.14608182452393867, -1.5703796136323465, 10.152686804413774, 17.931543960313533, 78.86592501486167, -6.135436630005442, -6.993667349083591]

        edemand_param["solar_irradiance"] = [152.77777777777777, 170.13888888888889, 187.5, 204.86111111111111, 222.22222222222223, 227.7777777777778, 233.3333333333333, 238.8888888888889, 244.44444444444449, 247.22222222222223, 250.0, 252.7777777777778, 255.5555555555556, 241.66666666666669, 227.7777777777778, 213.88888888888889, 200.0, 180.5555555555556, 161.11111111111111, 141.66666666666669, 122.22222222222224, 97.91666666666669, 73.61111111111111, 49.30555555555557, 25.0, 18.75, 12.5, 6.250000000000001, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        edemand_param["air_temperature"] = [279.25, 279.54999999999995, 279.85, 280.15, 280.45, 280.7, 280.95, 281.2, 281.45, 281.775, 282.1, 282.42499999999995, 282.75, 282.85, 282.95, 283.04999999999995, 283.15, 283.15, 283.15, 283.15, 283.15, 282.95, 282.75, 282.54999999999995, 282.35, 282.275, 282.2, 282.125, 282.04999999999995, 282.125, 282.2, 282.275, 282.35, 282.375, 282.4, 282.42499999999995, 282.45, 282.375, 282.29999999999995, 282.225, 282.15, 282.025, 281.9, 281.775, 281.65, 281.625, 281.6, 281.575]
        edemand_param["soil_temperature"] = [281.3833333333333, 281.37916666666666, 281.375, 281.37083333333334, 281.3666666666666, 281.36249999999995, 281.3583333333333, 281.35416666666663, 281.35, 281.3458333333333, 281.34166666666664, 281.3375, 281.3333333333333, 281.32916666666665, 281.325, 281.3208333333333, 281.31666666666666, 281.3125, 281.30833333333334, 281.3041666666666, 281.29999999999995, 281.2958333333333, 281.29166666666663, 281.2875, 281.2833333333333, 281.27916666666664, 281.275, 281.2708333333333, 281.26666666666665, 281.2625, 281.2583333333333, 281.25416666666666, 281.25, 281.24583333333334, 281.2416666666666, 281.23749999999995, 281.2333333333333, 281.22916666666663, 281.225, 281.2208333333333, 281.21666666666664, 281.2125, 281.2083333333333, 281.20416666666665, 281.2, 281.1958333333333, 281.19166666666666, 281.1875]

        esdl_id_to_test = "5c19dcff-b004-4644-99b9-f42d15a34f3a"
        ret_val = service.calculate_dispatch(edemand_param, datetime(2020,1,14), TimeStepInformation(0,1), esdl_id_to_test, energy_system)

        expected_active_power_single_phase = edemand_param['active_power'][0] / 3
        expected_reactive_power_single_phase = edemand_param['reactive_power'][0] / 3
        expected_active_power = [expected_active_power_single_phase, expected_active_power_single_phase, expected_active_power_single_phase]
        expected_reactive_power = [expected_reactive_power_single_phase, expected_reactive_power_single_phase, expected_reactive_power_single_phase]

        for key in ret_val.keys():
            if key == "aggregated_active_power":
                self.assertListEqual(ret_val[key], expected_active_power)
            elif key == "aggregated_reactive_power":
                self.assertListEqual(ret_val[key], expected_reactive_power)
            else:
                self.assertEqual(ret_val[key], 0.0)

if __name__ == '__main__':
    unittest.main()
