from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import random
from typing import List
import unittest
from unittest.mock import MagicMock

from dots_infrastructure.EsdlProfileParsingClasses import ParsedDateTimeProfile, ParsedTimeSeriesProfile, convert_parsed_datetime_profile_to_time_series_profile
import esdl
from EConnectionService.EConnection import CalculationServiceEConnection
from EConnectionService.heatpump_service import ServiceHeatPump
from dots_infrastructure.DataClasses import EsdlId, SimulatorConfiguration, TimeStepInformation
from dots_infrastructure.test_infra.InfluxDBMock import LOGGER, InfluxDBMock
import helics as h
from esdl.esdl_handler import EnergySystemHandler

from dots_infrastructure import CalculationServiceHelperFunctions



BROKER_TEST_PORT = 23404
START_DATE_TIME = datetime(2023, 1, 1, 0, 0, 0)
SIMULATION_DURATION_IN_SECONDS = 900*50
TIME_STEP_SIZE = 900
AMOUNT_OF_TIMESTEPS = int(SIMULATION_DURATION_IN_SECONDS / TIME_STEP_SIZE)
ENVIRONMENTAL_PROFILES_ID = "7738f333-8cea-4dde-a60b-3c366c171a68"

def simulator_environment_e_connection():
    return 

@dataclass
class EmsTestParam:
    esdl_id : str
    expected_outcomes : List[str]
    esdl_file : str

class GenerateProfileClass:

    def load_esdl_file(self, file_path) -> tuple[esdl.EnergySystem, dict[str, str]]:
        esh = EnergySystemHandler()
        esh.load_file(file_path)
        energy_system =  esh.get_energy_system()
        all_econnections = [esdl_obj for esdl_obj in energy_system.eAllContents() if isinstance(esdl_obj, esdl.EConnection)]
        econnection_heatpump_mapping = {}
        for econnection in all_econnections:
            for asset in econnection.eContainer().eAllContents():
                if isinstance(asset, esdl.HeatPump):
                    econnection_heatpump_mapping[econnection.id] = asset.id
        return energy_system, econnection_heatpump_mapping

    def parse_profile(self, profile : esdl.StaticProfile) -> ParsedTimeSeriesProfile:
        if isinstance(profile, esdl.DateTimeProfile):
            date_time_profile = ParsedDateTimeProfile(profile)
            return convert_parsed_datetime_profile_to_time_series_profile(date_time_profile)
        elif isinstance(profile, esdl.TimeSeriesProfile):
            return ParsedTimeSeriesProfile(profile)
        else:
            raise ValueError(f"Profile {profile.name} is of an unsupported type")

    def init_weahther_data(self, energy_system):
        # set in setup
        self.solar_irradiances: dict[EsdlId, ParsedTimeSeriesProfile] = {}
        self.air_temperatures:  dict[EsdlId, ParsedTimeSeriesProfile] = {}
        self.soil_temperatures: dict[EsdlId, ParsedTimeSeriesProfile] = {}

        # Get profiles from the ESDL
        for obj in energy_system.eAllContents():
            if hasattr(obj, "id") and obj.id == ENVIRONMENTAL_PROFILES_ID:
                environmental_profiles = obj
                break

        solar_irradiance_profile = environmental_profiles.solarIrradianceProfile
        air_temperature_profile  = environmental_profiles.outsideTemperatureProfile
        soil_temperature_profile = environmental_profiles.soilTemperatureProfile

        self.solar_irradiances[ENVIRONMENTAL_PROFILES_ID] = self.parse_profile(solar_irradiance_profile)
        self.air_temperatures[ENVIRONMENTAL_PROFILES_ID]  = self.parse_profile(air_temperature_profile)
        self.soil_temperatures[ENVIRONMENTAL_PROFILES_ID] = self.parse_profile(soil_temperature_profile)
    
    def init_e_connection_service(self, energy_system : esdl.EnergySystem):
        service = CalculationServiceEConnection()
        service.influx_connector = InfluxDBMock()
        service.init_calculation_service(energy_system)
        return service

    def init_heat_pump_service(self, energy_system : esdl.EnergySystem) -> ServiceHeatPump:
        heat_pump_service = ServiceHeatPump()
        all_heatpump_ids = [esdl_obj.id for esdl_obj in energy_system.eAllContents() if isinstance(esdl_obj, esdl.HeatPump)]
        heat_pump_service.init_calculation_service(energy_system, all_heatpump_ids)
        return heat_pump_service

    def celcius_to_kelvin(self, celcius : float):
        return celcius + 273.15

    def generate_profiles(self):
        # arrange
        energy_system, econnection_heatpump_mapping = self.load_esdl_file(str(Path(__file__).parent / 'test-heatpump-extraction.esdl'))
        sim_config = SimulatorConfiguration("EConnection", list(econnection_heatpump_mapping.keys()), "Mock-Econnection", "127.0.0.1", BROKER_TEST_PORT, "test-id", SIMULATION_DURATION_IN_SECONDS, START_DATE_TIME, "test-host", "test-port", "test-username", "test-password", "test-database-name", h.HelicsLogLevel.TRACE, ["EConnection"])
        CalculationServiceHelperFunctions.get_simulator_configuration_from_environment = MagicMock(return_value = sim_config)
        service = self.init_e_connection_service(energy_system)
        heat_pump_service = self.init_heat_pump_service(energy_system)
        self.init_weahther_data(energy_system)

        heat_power_to_tank_dhw = []
        heat_power_to_buffer = [] 
        heat_power_to_dhw = [] 
        heat_power_to_house = [] 
        window_size_in_seconds = 43200
        for econnection_id, heatpump_id in econnection_heatpump_mapping.items():
            current_date_time = datetime(2020,1,1,0,0,0)

            for i in range(1, AMOUNT_OF_TIMESTEPS + 1):

                edemand_param = {}

                # Electricity demand
                edemand_param['active_power'] = [52.0, 48.0, 152.0, 55.9999999999999, 48.0, 52.0, 444.0, 284.0, 327.9999999999999, 348.0, 316.0, 572.0000000000001, 276.0, 272.0, 272.0, 272.0, 100.0, 72.0, 72.0, 72.0, 68.0, 72.0, 68.0, 76.0, 72.0, 68.0, 72.0, 72.0, 68.0, 92.0, 148.0, 140.0, 140.0, 136.0, 132.0, 132.0, 163.9999999999999, 288.0, 360.0, 387.9999999999999, 384.0, 392.0, 387.9999999999999, 436.0, 392.0, 387.9999999999999, 468.0, 452.0]
                edemand_param['reactive_power'] = [17.091573469300883, 15.776837048585431, 49.9599839871872, 18.406309890016303, 15.776837048585431, 17.091573469300883, 145.93574269941524, 93.34628587079713, 107.80838649866708, 114.38206860224437, 103.86417723652076, 188.00730816230976, 90.71681302936624, 89.40207660865077, 89.40207660865077, 89.40207660865077, 32.86841051788632, 23.665255572878145, 23.665255572878145, 23.665255572878145, 22.350519152162693, 23.665255572878145, 22.350519152162693, 24.9799919935936, 23.665255572878145, 22.350519152162693, 23.665255572878145, 23.665255572878145, 22.350519152162693, 30.23893767645541, 48.645247566471745, 46.01577472504084, 46.01577472504084, 44.70103830432539, 43.38630188360994, 43.38630188360994, 53.90419324933352, 94.66102229151258, 118.32627786439073, 127.52943280939887, 126.21469638868345, 128.84416923011435, 127.52943280939887, 143.30626985798435, 128.84416923011435, 127.52943280939887, 153.82416122370796, 148.56521554084614]
                edemand_param['day_ahead_prices'] = [920.23, 422.1, 153.79, 291.76, 457.0, 731.33, 553.59, 434.58, 800.85, 664.14, 241.39, 94.78, 732.2, 980.45, 235.4, 36.99, 67.3, 402.98, 650.85, 673.75, 87.93, 840.2, 335.75, 703.71, 222.41, 542.59, 419.94, 863.11, 182.91, 627.8, 666.93, 702.67, 562.09, 275.02, 468.02, 893.98, 731.37, 732.65, 667.9, 13.93, 546.42, 327.63, 389.7, 621.82, 369.75, 911.0, 669.27, 332.02]

                to_date_time = current_date_time + timedelta(seconds=window_size_in_seconds)
                solar_irradiance = self.solar_irradiances[ENVIRONMENTAL_PROFILES_ID].get_data_in_timeseries_format_interpolated(current_date_time, to_date_time, TIME_STEP_SIZE)
                air_temperature = self.air_temperatures[ENVIRONMENTAL_PROFILES_ID].get_data_in_timeseries_format_interpolated(current_date_time, to_date_time, TIME_STEP_SIZE)
                soil_temperature = self.soil_temperatures[ENVIRONMENTAL_PROFILES_ID].get_data_in_timeseries_format_interpolated(current_date_time, to_date_time, TIME_STEP_SIZE)
                edemand_param["solar_irradiance"] = solar_irradiance
                edemand_param["air_temperature"] = [self.celcius_to_kelvin(temp) for temp in air_temperature]
                edemand_param["soil_temperature"] = [self.celcius_to_kelvin(temp) for temp in soil_temperature]

                to_date_time = current_date_time + timedelta(seconds=TIME_STEP_SIZE)
                current_solar_irradiance = self.solar_irradiances[ENVIRONMENTAL_PROFILES_ID].get_data(current_date_time, to_date_time)[0]
                current_air_temperature = self.air_temperatures[ENVIRONMENTAL_PROFILES_ID].get_data(current_date_time, to_date_time)[0]
                current_soil_temperature = self.soil_temperatures[ENVIRONMENTAL_PROFILES_ID].get_data(current_date_time, to_date_time)[0]

                current_temps = {}
                current_temps["solar_irradiance"] = current_solar_irradiance
                current_temps["air_temperature"] = self.celcius_to_kelvin(current_air_temperature)
                current_temps["soil_temperature"] = self.celcius_to_kelvin(current_soil_temperature)

                temperatures = heat_pump_service.send_temperatures(current_temps, current_date_time, TimeStepInformation(i, AMOUNT_OF_TIMESTEPS), heatpump_id, energy_system)

                # heatpump
                edemand_param["dhw_temperature"] = temperatures["dhw_temperature"]
                edemand_param["buffer_temperature"] = temperatures["buffer_temperature"]
                edemand_param["house_temperatures"] = temperatures["house_temperatures"]  
                if i == 47:
                    bla = 5

                # Execute
                ret_val_ems = service.calculate_dispatch(edemand_param, current_date_time, TimeStepInformation(i, AMOUNT_OF_TIMESTEPS), econnection_id, energy_system)

                heat_power_to_tank_dhw.append(ret_val_ems["heat_power_to_tank_dhw"])
                heat_power_to_buffer.append(ret_val_ems["heat_power_to_buffer"])
                heat_power_to_dhw.append(ret_val_ems["heat_power_to_dhw"])
                heat_power_to_house.append(ret_val_ems["heat_power_to_house"])

                ret_val_ems["solar_irradiance"] = current_solar_irradiance
                ret_val_ems["air_temperature"] = self.celcius_to_kelvin(current_air_temperature)
                ret_val_ems["soil_temperature"] = self.celcius_to_kelvin(current_soil_temperature)

                # LOGGER.info(f"heat_power_to_tank_dhw: {heat_power_to_tank_dhw}")
                # LOGGER.info(f"heat_power_to_buffer: {heat_power_to_buffer}")
                # LOGGER.info(f"heat_power_to_dhw: {heat_power_to_dhw}")
                # LOGGER.info(f"heat_power_to_house: {heat_power_to_house}")
                heat_pump_service.update_temperatures(ret_val_ems, current_date_time, TimeStepInformation(i, AMOUNT_OF_TIMESTEPS), heatpump_id, energy_system)
                LOGGER.info(f"Finished iteration at time {current_date_time} timestep {i}")
                current_date_time = current_date_time + timedelta(seconds = TIME_STEP_SIZE)


if __name__ == '__main__':
    class_instance = GenerateProfileClass()
    class_instance.generate_profiles()
