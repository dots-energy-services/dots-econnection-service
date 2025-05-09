# -*- coding: utf-8 -*-
from datetime import datetime
import helics as h
from dots_infrastructure.DataClasses import EsdlId, HelicsCalculationInformation, PublicationDescription, SubscriptionDescription, TimeStepInformation, TimeRequestType
from dots_infrastructure.HelicsFederateHelpers import HelicsSimulationExecutor
from dots_infrastructure.Logger import LOGGER
from esdl import esdl, EnergySystem

import json
import numpy as np
from typing import Optional, List
from EConnectionService.portfolio_optimization import PortfolioOptimizationProblem
from dots_infrastructure.CalculationServiceHelperFunctions import get_single_param_with_name


class CalculationServiceEConnection(HelicsSimulationExecutor):

    def __init__(self):
        super().__init__()

        subscriptions_values = [
            SubscriptionDescription(esdl_type="EnvironmentalProfiles",
                                    input_name="solar_irradiance",
                                    input_unit="Wm2",
                                    input_type=h.HelicsDataType.VECTOR),
            SubscriptionDescription(esdl_type="EnvironmentalProfiles",
                                    input_name="air_temperature",
                                    input_unit="K",
                                    input_type=h.HelicsDataType.VECTOR),
            SubscriptionDescription(esdl_type="EnvironmentalProfiles",
                                    input_name="soil_temperature",
                                    input_unit="K",
                                    input_type=h.HelicsDataType.VECTOR),
            SubscriptionDescription(esdl_type="ElectricityDemand",
                                    input_name="active_power",
                                    input_unit="W",
                                    input_type=h.HelicsDataType.VECTOR),
            SubscriptionDescription(esdl_type="ElectricityDemand",
                                    input_name="reactive_power",
                                    input_unit="VAr",
                                    input_type=h.HelicsDataType.VECTOR),
            SubscriptionDescription(esdl_type="PVInstallation",
                                    input_name="potential_active_power",
                                    input_unit="W",
                                    input_type=h.HelicsDataType.VECTOR),
            SubscriptionDescription(esdl_type="HeatPump",
                                    input_name="dhw_temperature",
                                    input_unit="K",
                                    input_type=h.HelicsDataType.DOUBLE),
            SubscriptionDescription(esdl_type="HeatPump",
                                    input_name="buffer_temperature",
                                    input_unit="K",
                                    input_type=h.HelicsDataType.DOUBLE),
            SubscriptionDescription(esdl_type="HeatPump",
                                    input_name="house_temperatures",
                                    input_unit="K",
                                    input_type=h.HelicsDataType.VECTOR),
            SubscriptionDescription(esdl_type="HybridHeatPump",
                                    input_name="buffer_temperature",
                                    input_unit="K",
                                    input_type=h.HelicsDataType.DOUBLE),
            SubscriptionDescription(esdl_type="HybridHeatPump",
                                    input_name="house_temperatures",
                                    input_unit="K",
                                    input_type=h.HelicsDataType.VECTOR),
            SubscriptionDescription(esdl_type="EVChargingStation",
                                    input_name="state_of_charge_ev",
                                    input_unit="J",
                                    input_type=h.HelicsDataType.DOUBLE)
        ]

        publication_values = [
            PublicationDescription(global_flag=True, 
                                   esdl_type="EConnection", 
                                   output_name="aggregated_active_power",
                                   output_unit="W", 
                                   data_type=h.HelicsDataType.VECTOR),
            PublicationDescription(global_flag=True,
                                   esdl_type="EConnection",
                                   output_name="aggregated_reactive_power",
                                   output_unit="VAr",
                                   data_type=h.HelicsDataType.VECTOR),
            PublicationDescription(global_flag=True,
                                   esdl_type="EConnection",
                                   output_name="dispatch_pv",
                                   output_unit="W",
                                   data_type=h.HelicsDataType.DOUBLE),
            PublicationDescription(global_flag=True,
                                   esdl_type="EConnection",
                                   output_name="dispatch_ev",
                                   output_unit="W",
                                   data_type=h.HelicsDataType.DOUBLE),
            PublicationDescription(global_flag=True,
                                   esdl_type="EConnection",
                                   output_name="heat_power_to_tank_dhw",
                                   output_unit="W",
                                   data_type=h.HelicsDataType.DOUBLE),
            PublicationDescription(global_flag=True,
                                   esdl_type="EConnection",
                                   output_name="heat_power_to_buffer",
                                   output_unit="W",
                                   data_type=h.HelicsDataType.DOUBLE),
            PublicationDescription(global_flag=True,
                                   esdl_type="EConnection",
                                   output_name="heat_power_to_dhw",
                                   output_unit="W",
                                   data_type=h.HelicsDataType.DOUBLE),
            PublicationDescription(global_flag=True,
                                   esdl_type="EConnection",
                                   output_name="heat_power_to_house",
                                   output_unit="W",
                                   data_type=h.HelicsDataType.DOUBLE),
            PublicationDescription(global_flag=True,
                                   esdl_type="EConnection",
                                   output_name="heat_power_to_buffer_hhp",
                                   output_unit="W",
                                   data_type=h.HelicsDataType.DOUBLE),
            PublicationDescription(global_flag=True,
                                   esdl_type="EConnection",
                                   output_name="heat_power_to_house_hhp",
                                   output_unit="W",
                                   data_type=h.HelicsDataType.DOUBLE)
        ]

        e_connection_period_in_seconds = 900
        self.ems_time_step_seconds = e_connection_period_in_seconds

        calculation_information = HelicsCalculationInformation(
            time_period_in_seconds=e_connection_period_in_seconds,
            offset=0, 
            uninterruptible=False, 
            wait_for_current_time_update=False, 
            terminate_on_error=True, 
            calculation_name="calculate_dispatch",
            inputs=subscriptions_values, 
            outputs=publication_values, 
            calculation_function=self.calculate_dispatch
        )
        self.add_calculation(calculation_information)

    def init_calculation_service(self, energy_system: esdl.EnergySystem):
        LOGGER.info("init calculation service")

        # 1. Initialization
        # Containers for storing connection specific data
        self.esdl_objects: dict[EsdlId, esdl] = {}
        self.asset_portfolios: dict[EsdlId, List] = {}
        self.energy_contracts: dict[EsdlId, str] = {}
        self.got_ems: dict[EsdlId, bool] = {}
        self.static_prices: dict[EsdlId, float] = {}
        self.dynamic_flat_prices: dict[EsdlId, float] = {}

        # Fixed global data, the same for all econnections
        self.optimization_horizon = 48  # number of time steps
        self.round_decimals = 5

        # Dynamic global data, the same for all econnections
        self.da_prices: Optional[List[float]] = None

        # Set up econnection specific data
        for esdl_id in self.simulator_configuration.esdl_ids:
            for obj in energy_system.eAllContents():
                if hasattr(obj, "id") and obj.id == esdl_id:
                    self.esdl_objects[esdl_id] = obj
                    asset_portfolio = self.get_asset_portfolio_from_econnection(self.esdl_objects[esdl_id])
                    self.asset_portfolios[esdl_id] = asset_portfolio
                    self.set_got_ems(esdl_id)
                    self.set_energy_contract_data(esdl_id)

        # 2. Set values
        self.set_initial_da_prices(energy_system)
        self.set_tariff_data(energy_system)

    def get_asset_portfolio_from_econnection(self, econnection: esdl.EConnection) -> dict:
        """
        Get the esdl objects and their phases in the house of the econnection
        asset_portfolio = {'electricity_demand': {'esdl_object': ElectricityDemand, 'phases': [True, True, True]}, ...}
        The phases entry is always a list of length 3 with bools to indicate to which phase the asset is connected
        """
        asset_portfolio = dict()
        if not isinstance(econnection.eContainer(), esdl.Building):
            raise ValueError(f'Econnection {econnection.id} is not in a building')
        else:
            assets = ["ElectricityDemand", "PVInstallation", "Battery", "HeatPump", "HybridHeatPump", "EVChargingStation"]
            building = econnection.eContainer()
            for asset in building.asset:
                asset_name = type(asset).__name__
                if asset_name in assets:
                    if asset_name in asset_portfolio:
                        raise ValueError(f'There was already a {asset_name} connected to Econnection {econnection.id}')
                    else:
                        asset_portfolio[asset_name] = {'esdl_object': asset, 'phases': self.get_phases_from_asset(asset)}

        return asset_portfolio

    @staticmethod
    def get_phases_from_asset(asset: esdl.EnergyAsset) -> list:
        """
        This function assumes that every asset is connected to 1 or more ElectricityNetwork objects
        Every ElectricityNetwork corresponds with 1 phase
        We assume that the last character of its name represents the phase (1, 2, or 3)
        """
        phases = [False, False, False]
        for port in asset.port:
            for connected_port in port.connectedTo:
                connected_asset = connected_port.eContainer()
                if isinstance(connected_asset, esdl.ElectricityNetwork):
                    phase_string = connected_asset.name[-1]
                    if not phase_string.isdigit():
                        raise ValueError(f'Electricity Grid name {connected_asset.name} does not end with an integer')
                    else:
                        phase = int(phase_string)
                        phases[phase - 1] = True
        assert phases != [False, False, False], 'Asset unconnected to Electricity Networks'

        return phases

    def calculate_dispatch(self,
                           param_dict: dict,
                           simulation_time: datetime,
                           time_step_number: TimeStepInformation,
                           esdl_id: EsdlId,
                           energy_system: EnergySystem):
        """
        This function calculates the dispatch of all assets in the portfolio of the Econnection. It does so by taking
        the following steps:
        - Create a portfolio optimization problem (single phase)
        - Solves the model for the dispatch of the assets
        - read the return values from the model
        - compute the (3 phase unbalanced) dispatch
        """
        LOGGER.info("calculation 'calculate_dispatch' started")
        # START user calc

        # Create problem if there is an EMS
        # If not: set load to the baseload and set all dispatch to 0
        if self.got_ems[esdl_id]:
            problem = self.create_portfolio_optimization_problem(param_dict, time_step_number, esdl_id)

            # Solve problem
            problem.solve(mip_gap=0.15)  # mip_gap=0.07
            LOGGER.info("Optimization problem solved")

            # Get peak tariff if necessary
            if self.is_variable_peak_tariff:
                self.peak_costs[esdl_id] = problem.get_first_value_from_component('peak_costs')

            # Get results
            ret_val = self.get_return_values_from_problem(problem, esdl_id)
        else:
            ret_val = self.get_return_values_no_ems(param_dict, esdl_id)

        # Store results
        self.store_return_values(ret_val, simulation_time, esdl_id)

        return ret_val

    def create_portfolio_optimization_problem(self,
                                              param_dict: dict,
                                              time_step_number: TimeStepInformation,
                                              esdl_id: EsdlId):
        """
        Builds the optimization problem in the following steps:
        - Add index sets
        - Add assets based on the assets in the asset portfolio constructed in the setup
        - Create the energy balance in the house
        - Create the incentives for the house
            * costs from buying electricity
            * revenues from selling electricity
            * costs from grid tariffs, of which 3 are implemented
        """

        time_step_nr = time_step_number.current_time_step_number
        asset_portfolio = self.asset_portfolios[esdl_id]

        # Create optimization problem
        problem = PortfolioOptimizationProblem()
        time_params = {'n_steps': self.optimization_horizon,
                       'dt': self.ems_time_step_seconds,
                       'time_step_nr': time_step_nr}
        problem.create_time(time_params)

        # Add asset specific components
        if 'ElectricityDemand' in asset_portfolio:
            active_power = get_single_param_with_name(param_dict, "active_power")
            active_power = [round(p, self.round_decimals) for p in active_power]
            problem.create_electricity_demand(active_power)
        if 'PVInstallation' in asset_portfolio:
            potential_active_power = get_single_param_with_name(param_dict, "potential_active_power")
            potential_active_power = [round(p, self.round_decimals) for p in potential_active_power]
            problem.create_pv(potential_active_power)
        if 'Battery' in asset_portfolio:
            battery = asset_portfolio['Battery']['esd_object']
            state_of_charge = param_dict['energy']
            state_of_charge = round(state_of_charge, self.round_decimals)
            problem.create_battery(battery, state_of_charge)
        if ('HeatPump' in asset_portfolio) or ('HybridHeatPump' in asset_portfolio):
            # Weather inputs
            air_temperature = get_single_param_with_name(param_dict, "air_temperature")
            air_temperature = [round(temp, self.round_decimals) for temp in air_temperature]

            soil_temperature = get_single_param_with_name(param_dict, "soil_temperature")
            soil_temperature = [round(temp, self.round_decimals) for temp in soil_temperature]

            solar_irradiance = get_single_param_with_name(param_dict, "solar_irradiance")
            solar_irradiance = [round(temp, self.round_decimals) for temp in solar_irradiance]

            # Inputs common to HeatPump and HybridHeatPump
            buffer_temperature = get_single_param_with_name(param_dict, "buffer_temperature")
            buffer_temperature = round(buffer_temperature, self.round_decimals)

            house_temperatures = get_single_param_with_name(param_dict, "house_temperatures")
            house_temperatures = [round(temp, self.round_decimals) for temp in house_temperatures]

            if 'HeatPump' in asset_portfolio:
                heat_pump = asset_portfolio['HeatPump']['esdl_object']
                # Heat pump specific inputs, related to domestic hot water (DHW)
                dhw_temperature = get_single_param_with_name(param_dict, "dhw_temperature")
                dhw_temperature = round(dhw_temperature, self.round_decimals)

                dhw_profile = heat_pump.port[0].profile[0].values  # assumes dhw profile is saved here
                dhw_profile_slice = dhw_profile[time_step_nr - 1:time_step_nr - 1 + self.optimization_horizon]
                dhw_profile_slice = [round(value, self.round_decimals) for value in dhw_profile_slice]

                problem.create_heat_pump(heat_pump,
                                         dhw_temperature,
                                         buffer_temperature,
                                         house_temperatures,
                                         air_temperature,
                                         soil_temperature,
                                         solar_irradiance,
                                         dhw_profile_slice)

            else:
                hybrid_heat_pump = asset_portfolio['HybridHeatPump']['esdl_object']

                problem.create_hybrid_heat_pump(hybrid_heat_pump,
                                                buffer_temperature,
                                                house_temperatures,
                                                air_temperature,
                                                soil_temperature,
                                                solar_irradiance)

        if 'EVChargingStation' in asset_portfolio:
            ev_charging_station = asset_portfolio['EVChargingStation']['esdl_object']
            state_of_charge = get_single_param_with_name(param_dict, "state_of_charge_ev")
            state_of_charge = round(state_of_charge, self.round_decimals)
            problem.create_ev_charging_station(ev_charging_station, state_of_charge)

        # Create energy balance constraints, grid tariff constraints and the objective function
        da_slice = self.da_prices[time_step_nr - 1:time_step_nr - 1 + self.optimization_horizon]
        problem.create_energy_balance(asset_portfolio)
        problem.create_buy_costs(self.energy_contracts[esdl_id],
                                 self.dynamic_flat_prices.get(esdl_id),  # possibly None
                                 self.static_prices.get(esdl_id),  # possibly None
                                 da_slice)

        problem.create_sell_revenues(self.energy_contracts[esdl_id],
                                     self.dynamic_flat_prices.get(esdl_id),  # possibly None
                                     self.static_prices.get(esdl_id),  # possibly None
                                     da_slice,
                                     self.is_feed_in_tariff,
                                     self.feed_in_price)  # possibly None

        # Add constrains and terms to objective function, depending on the presence of the grid tariffs
        is_grid_tariff = False
        if self.is_static_bw_tariff:
            is_grid_tariff = True
            problem.create_static_bw_tariff(self.static_bw_price_low,
                                            self.static_bw_price_high,
                                            self.static_bw_powers[esdl_id])
        if self.is_variable_tariff:
            is_grid_tariff = True
            problem.create_variable_tariff(self.variable_tariff[time_step_nr - 1:time_step_nr - 1 + self.optimization_horizon])
        if self.is_variable_peak_tariff:
            is_grid_tariff = True
            problem.create_variable_peak_tariff(self.variable_peak_tariff[time_step_nr - 1:time_step_nr - 1 + self.optimization_horizon],
                                                self.peak_costs[esdl_id])

        problem.create_objective_function(is_grid_tariff)

        return problem

    def get_return_values_no_ems(self, param_dict: dict, esdl_id: str):
        ret_val = {'dispatch_ev': 0.0, 'dispatch_pv': -0.0, 'heat_power_to_tank_dhw': 0.0, 'heat_power_to_buffer': 0.0,
                   'heat_power_to_dhw': 0.0, 'heat_power_to_house': 0.0, 'heat_power_to_buffer_hhp': 0.0,
                   'heat_power_to_house_hhp': 0.0, 'aggregated_active_power': [0.0, 0.0, 0.0],
                   'aggregated_reactive_power': [0.0, 0.0, 0.0]}

        aggregated_active_power = np.array([0.0, 0.0, 0.0])
        aggregated_reactive_power = np.array([0.0, 0.0, 0.0])

        asset_portfolio = self.asset_portfolios[esdl_id]

        active_power = get_single_param_with_name(param_dict, "active_power")[0]
        p, q = self.get_p_q_3ph_from_asset(asset_portfolio, 'ElectricityDemand', active_power)
        aggregated_active_power += p
        aggregated_reactive_power += q

        ret_val['aggregated_active_power'] = aggregated_active_power.tolist()
        ret_val['aggregated_reactive_power'] = aggregated_reactive_power.tolist()

        return ret_val

    def get_return_values_from_problem(self, problem: PortfolioOptimizationProblem, esdl_id: EsdlId):
        ret_val = {'dispatch_ev': 0.0, 'dispatch_pv': -0.0, 'heat_power_to_tank_dhw': 0.0, 'heat_power_to_buffer': 0.0,
                   'heat_power_to_dhw': 0.0, 'heat_power_to_house': 0.0, 'heat_power_to_buffer_hhp': 0.0,
                   'heat_power_to_house_hhp': 0.0, 'aggregated_active_power': [0.0, 0.0, 0.0],
                   'aggregated_reactive_power': [0.0, 0.0, 0.0]}

        aggregated_active_power = np.array([0.0, 0.0, 0.0])
        aggregated_reactive_power = np.array([0.0, 0.0, 0.0])

        asset_portfolio = self.asset_portfolios[esdl_id]

        if 'ElectricityDemand' in asset_portfolio:
            # Only grab the first value. The other values in the horizon don't matter
            p_edemand = problem.get_first_value_from_component('p_edemand')
            p, q = self.get_p_q_3ph_from_asset(asset_portfolio, 'ElectricityDemand', p_edemand)
            aggregated_active_power += p
            aggregated_reactive_power += q

        if 'PVInstallation' in asset_portfolio:
            p_use = - problem.get_first_value_from_component('p_pv_use')
            p_sell = - problem.get_first_value_from_component('p_pv_sell')
            p_pv = p_use + p_sell
            ret_val['dispatch_pv'] = p_pv

            p, q = self.get_p_q_3ph_from_asset(asset_portfolio, 'PVInstallation', p_pv)
            aggregated_active_power += p
            aggregated_reactive_power += q

        if 'Battery' in asset_portfolio:
            p_ch = problem.get_first_value_from_component('p_ch')
            p_bat_use = problem.get_first_value_from_component('p_bat_use')
            p_bat_sell = problem.get_first_value_from_component('p_bat_sell')
            p_battery = asset_portfolio['Battery'].chargeEfficiency * p_ch - asset_portfolio['Battery'].dischargeEfficiency * (p_bat_use - p_bat_sell)
            ret_val['dispatch_battery'] = p_battery

            p, q = self.get_p_q_3ph_from_asset(asset_portfolio, 'Battery', p_battery)
            aggregated_active_power += p
            aggregated_reactive_power += q

        if 'HeatPump' in asset_portfolio:
            p_hp = problem.get_first_value_from_component('p_hp')
            ret_val["heat_power_to_tank_dhw"] = problem.get_first_value_from_component('Q_to_dhw_tank')
            heat_element = problem.get_first_value_from_component('z_element_on') * problem.get_value_from_component('Q_element')
            ret_val["heat_power_to_tank_dhw"] += heat_element
            ret_val["heat_power_to_buffer"] = problem.get_first_value_from_component('Q_to_buffer')
            ret_val["heat_power_to_dhw"] = problem.get_first_value_from_component('Q_to_dhw')
            ret_val["heat_power_to_house"] = problem.get_first_value_from_component('Q_to_house')

            p, q = self.get_p_q_3ph_from_asset(asset_portfolio, 'HeatPump', p_hp)
            aggregated_active_power += p
            aggregated_reactive_power += q

        if 'HybridHeatPump' in asset_portfolio:
            p_hhp = problem.get_first_value_from_component('p_hhp')
            ret_val["heat_power_to_buffer_hhp"] = problem.get_first_value_from_component('Q_to_buffer')
            ret_val["heat_power_to_house"] = problem.get_first_value_from_component('Q_to_house')

            p, q = self.get_p_q_3ph_from_asset(asset_portfolio, 'HybridHeatPump', p_hhp)
            aggregated_active_power += p
            aggregated_reactive_power += q

        if 'EVChargingStation' in asset_portfolio:
            p_ev = problem.get_first_value_from_component('p_ev')
            ret_val['dispatch_ev'] = p_ev

            p, q = self.get_p_q_3ph_from_asset(asset_portfolio, 'EVChargingStation', p_ev)
            aggregated_active_power += p
            aggregated_reactive_power += q

        ret_val['aggregated_active_power'] = aggregated_active_power.tolist()
        ret_val['aggregated_reactive_power'] = aggregated_reactive_power.tolist()

        return ret_val

    def store_return_values(self, ret_val: dict, simulation_time: datetime, esdl_id: EsdlId):
        active_powers = ret_val['aggregated_active_power']
        reactive_powers = ret_val['aggregated_reactive_power']

        for i, name in enumerate(['apparent_power_ph1', 'apparent_power_ph2', 'apparent_power_ph3']):
            apparent_power = round(np.sqrt(active_powers[i] ** 2 + reactive_powers[i] ** 2), self.round_decimals)
            self.influx_connector.set_time_step_data_point(esdl_id, name, simulation_time, apparent_power)

        self.influx_connector.set_time_step_data_point(esdl_id, 'active_dispatch_ev', simulation_time, ret_val.get('dispatch_ev', 0.0))
        self.influx_connector.set_time_step_data_point(esdl_id, 'active_dispatch_pv', simulation_time, ret_val.get('dispatch_pv', 0.0))
        self.influx_connector.set_time_step_data_point(esdl_id, 'active_dispatch_hp', simulation_time, ret_val.get('dispatch_hp', 0.0))
        self.influx_connector.set_time_step_data_point(esdl_id, 'active_dispatch_hhp', simulation_time, ret_val.get('dispatch_hhp', 0.0))

    def get_p_q_3ph_from_asset(self, asset_portfolio: dict, asset_name: str, total_p: float) -> np.array:
        # Distribute p evenly over the connected phases
        # Calculate q based on the power factor of the asset
        p = np.zeros(3)
        if asset_name not in asset_portfolio:
            raise KeyError(f'Asset {asset_name} is not in asset_portfolio {asset_portfolio}')
        else:
            p[asset_portfolio[asset_name]['phases']] = total_p / sum(asset_portfolio[asset_name]['phases'])
            q = self.calculate_q(p, asset_portfolio[asset_name]['esdl_object'].powerFactor)

        return p, q

    def set_initial_da_prices(self, energy_system):
        services = energy_system.services
        da_prices = []
        for service in services.service:
            if isinstance(service, esdl.EnergyMarket):
                for el in service.marketPrice.element:
                    da_prices.append(el.value)
        assert len(da_prices) > 0, "No energy market prices found in esdl"
        self.da_prices = da_prices

    def set_tariff_data(self, energy_system):
        measures = energy_system.measures

        self.is_static_bw_tariff = False
        self.is_variable_tariff = False
        self.is_variable_peak_tariff = False
        self.is_feed_in_tariff = False
        self.feed_in_price = None
        for measure in measures.measure:
            if measure.name == 'static_bandwidth_tariff':
                LOGGER.info("Static Bandwidth tariff detected")
                self.is_static_bw_tariff = True
                self.static_bw_price_low = 0.0
                self.static_bw_price_high = measure.costInformation.variableOperationalCosts.value
                self.static_bw_powers = {esdl_id: self.esdl_objects[esdl_id].capacity for esdl_id
                                         in self.simulator_configuration.esdl_ids}

            if measure.name == 'variable_tariff':
                LOGGER.info("Variable tariff detected")
                self.is_variable_tariff = True
                price_profile = measure.costInformation.variableOperationalCosts
                self.variable_tariff = [el.value for el in price_profile.element]

            if measure.name == 'variable_peak_tariff':
                LOGGER.info("Variable peak tariff detected")
                self.is_variable_peak_tariff = True
                price_profile = measure.costInformation.variableOperationalCosts
                self.variable_peak_tariff = [el.value for el in price_profile.element]
                self.peak_costs = {esdl_id: 0.0 for esdl_id in self.simulator_configuration.esdl_ids}

            if measure.name == 'feed_in_tariff':
                LOGGER.info("Feed-in tariff detected")
                self.is_feed_in_tariff = True
                self.feed_in_price = measure.costInformation.variableOperationalCosts.value

    def set_got_ems(self, esdl_id: str):
        description_dict = json.loads(self.esdl_objects[esdl_id].description)
        self.got_ems[esdl_id] = description_dict['got_ems']

    def set_energy_contract_data(self, esdl_id: str):
        description_dict = json.loads(self.esdl_objects[esdl_id].description)
        if description_dict['got_ems']:  # only connections with an ems have a contract
            energy_contract = description_dict['energy_contract']
            self.energy_contracts[esdl_id] = description_dict['energy_contract']
            if energy_contract == 'dynamic':
                self.dynamic_flat_prices[esdl_id] = description_dict['flat_price']
            elif energy_contract == 'static':
                self.static_prices[esdl_id] = description_dict['price']
            else:
                raise ValueError(f'Detected contract type {energy_contract} for EMS {esdl_id} '
                                 f'which is neither dynamic or static ')

    @staticmethod
    def calculate_q(p: np.array, pf: float) -> np.array:
        return np.sqrt(1-pf**2)/pf * p


if __name__ == "__main__":
    helics_simulation_executor = CalculationServiceEConnection()
    helics_simulation_executor.start_simulation()
    helics_simulation_executor.stop_simulation()
