# -*- coding: utf-8 -*-
from datetime import datetime
from typing import List
from esdl import esdl

from dots_infrastructure.DataClasses import EsdlId, TimeStepInformation
from dots_infrastructure.Logger import LOGGER
from esdl import EnergySystem
from dots_infrastructure.CalculationServiceHelperFunctions import get_vector_param_with_name, get_single_param_with_name

import json
import numpy as np

from EConnectionService.thermalsystems import HeatBuffer, House

class ServiceHeatPump:

    def init_calculation_service(self, energy_system: esdl.EnergySystem, esdl_ids : List[str]):
        self.hp_description_dicts: dict[EsdlId, dict[str, float]] = {}
        self.hp_esdl_power: dict[EsdlId, float] = {}

        self.dhw_tanks: dict[EsdlId, HeatBuffer] = {}
        self.buffers: dict[EsdlId, HeatBuffer] = {}
        self.houses: dict[EsdlId, House] = {}

        self.inv_capacitance_matrices: dict[EsdlId, np.array] = {}
        self.conductance_matrices: dict[EsdlId, np.array] = {}
        self.forcing_matrices: dict[EsdlId, np.array] = {}
        self.heatpump_period_in_seconds = 900
        
        for obj in energy_system.eAllContents():
            if hasattr(obj, "id") and isinstance(obj.eContainer(), esdl.Building) and obj.id in esdl_ids:
                esdl_id = obj.id
                hpsystem = obj
                building_description = json.loads(obj.eContainer().description)
                self.hp_description_dicts[esdl_id] = json.loads(hpsystem.description)
                self.hp_esdl_power[esdl_id] = hpsystem.power
                # Set Tanks
                buffer_capacitance = self.hp_description_dicts[esdl_id]['buffer_capacitance']
                dhw_capacitance = self.hp_description_dicts[esdl_id]['dhw_capacitance']
                self.buffers[esdl_id] = HeatBuffer(buffer_capacitance)
                self.dhw_tanks[esdl_id] = HeatBuffer(dhw_capacitance)
                LOGGER.debug(f'dhw_capacitance: {dhw_capacitance}')
                # Set Houses
                capacities = {'C_in': building_description['C_in'], 'C_out': building_description['C_out']}
                resistances = {'R_exch': building_description['R_exch'], 'R_floor': building_description['R_floor'],
                               'R_vent': building_description['R_vent'], 'R_cond': building_description['R_cond']}
                window_area = building_description['A_glass']
                self.houses[esdl_id] = House(capacities, resistances, window_area)



    def send_temperatures(self, param_dict : dict, simulation_time : datetime, time_step_number : TimeStepInformation, esdl_id : EsdlId, energy_system : EnergySystem):
        # START user calc
        LOGGER.info("calculation 'send_temperatures' started")
        LOGGER.debug(get_single_param_with_name(param_dict, "air_temperature"))

        predicted_solar_irradiances = get_single_param_with_name(param_dict, "solar_irradiance")
        predicted_air_temperatures = get_single_param_with_name(param_dict, "air_temperature")
        predicted_soil_temperatures = get_single_param_with_name(param_dict, "soil_temperature")

        # Check if the house and tank temperatures are properly initialized
        house = self.houses[esdl_id]
        buffer = self.buffers[esdl_id]
        dhw_tank = self.dhw_tanks[esdl_id]
        if (house.temperatures is None) or (buffer.temperature is None) or (dhw_tank.temperature is None):
            current_solar_irradiance = predicted_solar_irradiances
            current_air_temperature  = predicted_air_temperatures
            current_soil_temperature = predicted_soil_temperatures

            hp_description_dict = self.hp_description_dicts[esdl_id]

            dhw_tank.set_initial_temperature(hp_description_dict['dhw_temp_0'])
            buffer.set_initial_temperature(hp_description_dict['buffer_temp_0'])
            house.set_initial_temperatures(hp_description_dict['house_temp_0'],
                                           self.hp_esdl_power[esdl_id],
                                           current_air_temperature,
                                           current_soil_temperature,
                                           current_solar_irradiance)

            self.dhw_tanks[esdl_id] = dhw_tank
            self.buffers[esdl_id] = buffer
            self.houses[esdl_id] = house

            house_temperatures_list = house.temperatures.tolist()
        else:
            house_temperatures_list = house.temperatures


        ret_val = {}
        ret_val["dhw_temperature"]      = dhw_tank.temperature
        ret_val["buffer_temperature"]   = buffer.temperature
        ret_val["house_temperatures"]   = house_temperatures_list
        LOGGER.info(f"House temperatures: {house.temperatures}")

        return ret_val
    
    def update_temperatures(self, param_dict : dict, simulation_time : datetime, time_step_number : TimeStepInformation, esdl_id : EsdlId, energy_system : EnergySystem):
        # START user calc
        LOGGER.info("calculation 'update_temperatures' started")
        predicted_solar_irradiances = get_single_param_with_name(param_dict, "solar_irradiance")
        predicted_air_temperatures = get_single_param_with_name(param_dict, "air_temperature")
        predicted_soil_temperatures = get_single_param_with_name(param_dict, "soil_temperature")
        heat_to_dhw_tank = get_single_param_with_name(param_dict, "heat_power_to_tank_dhw")
        heat_to_dhw = get_single_param_with_name(param_dict, "heat_power_to_dhw")
        heat_to_buffer = get_single_param_with_name(param_dict, "heat_power_to_buffer")
        heat_to_house = get_single_param_with_name(param_dict,"heat_power_to_house")
        
        # if time_step_number.current_time_step_number == 47:
        #     heat_to_house = 5000
        #     heat_to_buffer = 4000


        current_air_temperature = predicted_air_temperatures
        current_soil_temperature = predicted_soil_temperatures
        current_solar_irradiance = predicted_solar_irradiances

        dhw_tank = self.dhw_tanks[esdl_id]
        buffer = self.buffers[esdl_id]
        house = self.houses[esdl_id]

        LOGGER.info(f"esdl id: {esdl_id}")
        LOGGER.info(f"dhw temperature before: {dhw_tank.temperature}")
        LOGGER.info(f"buffer temperature before: {buffer.temperature}")
        LOGGER.info(f"house temperatures before: {house.temperatures}")

        LOGGER.info(f"heat to dhw: {heat_to_dhw}")
        LOGGER.info(f"heat to dhw tank: {heat_to_dhw_tank}")
        LOGGER.info(f"heat to house: {heat_to_house}")
        LOGGER.info(f"heat to buffer: {heat_to_buffer}")

        # Update temperatures
        dhw_tank.update_temperature(self.heatpump_period_in_seconds,
                                    heat_to_dhw,
                                    heat_to_dhw_tank)
        buffer.update_temperature(self.heatpump_period_in_seconds,
                                  heat_to_house,
                                  heat_to_buffer)
        house.update_temperatures(self.heatpump_period_in_seconds,
                                  current_air_temperature,
                                  current_soil_temperature,
                                  current_solar_irradiance,
                                  heat_to_house)

        LOGGER.info(f"dhw temperature after: {dhw_tank.temperature}")
        LOGGER.info(f"buffer temperature after: {buffer.temperature}")
        LOGGER.info(f"house temperatures after: {house.temperatures}")

        dhw_tank_temperature = dhw_tank.temperature
        house_temperatures = house.temperatures
        buffer_temperature = buffer.temperature

        # Check whether temperatures did not surpass the limits due to some numerical error
        lower_bound_dhw_tank = self.hp_description_dicts[esdl_id]['dhw_temp_min']
        upper_bound_dhw_tank = self.hp_description_dicts[esdl_id]['dhw_temp_max']
        lower_bound_buffer = self.hp_description_dicts[esdl_id]['buffer_temp_min']
        upper_bound_buffer = self.hp_description_dicts[esdl_id]['buffer_temp_max']
        lower_bound_house = self.hp_description_dicts[esdl_id]['house_temp_min']

        # Correct errors up till error eps
        eps = 1.0e-2
        if abs(dhw_tank_temperature - lower_bound_dhw_tank) < eps:
            dhw_tank_temperature = lower_bound_dhw_tank + eps
        if abs(dhw_tank_temperature - upper_bound_dhw_tank) < eps:
            dhw_tank_temperature = upper_bound_buffer - eps
        if abs(buffer_temperature - lower_bound_buffer) < eps:
            buffer_temperature = lower_bound_buffer + eps
        if abs(buffer_temperature - upper_bound_buffer) < eps:
            buffer_temperature = upper_bound_buffer - eps
        if abs(house_temperatures[0] - lower_bound_house) < eps:
            house_temperatures[0] = lower_bound_house + eps

        # Raise errors if the values are still not within boundaries
        if (dhw_tank_temperature < lower_bound_dhw_tank) or (dhw_tank_temperature > upper_bound_dhw_tank):
            raise ValueError(f"Heat pump {esdl_id} is charged over/under its dhw capacity")
        if (buffer_temperature < lower_bound_buffer) or (buffer_temperature > upper_bound_buffer):
            raise ValueError(f"Heat pump {esdl_id} is charged over/under its buffer capacity")
        if house_temperatures[0] < lower_bound_house:
            raise ValueError(f"Heat pump {esdl_id} is charged over/under its house capacity")

        # Save as state
        dhw_tank.temperature = dhw_tank_temperature
        buffer.temperature = buffer_temperature
        house.temperatures = house_temperatures.tolist()
        self.dhw_tanks[esdl_id] = dhw_tank
        self.buffers[esdl_id] = buffer
        self.houses[esdl_id] = house

        LOGGER.info("calculation 'update_temperatures' finished")

        ret_val = {}
        return ret_val
