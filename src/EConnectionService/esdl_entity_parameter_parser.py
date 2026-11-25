from datetime import datetime, timedelta
import json
from typing import List
import esdl
from dataclasses import dataclass
import math

from dots_infrastructure.DataClasses import TimeStepInformation
from dots_infrastructure.Logger import LOGGER


def celsius_to_kelvin(temperature_c):
    """Convert a temperature from Celsius to Kelvin."""
    return temperature_c + 273.15 if temperature_c is not None else None

@dataclass
class BuildingParameters:
    C_in_kwh : float
    C_out_kwh : float
    R_exch : float
    R_floor : float
    R_vent : float
    R_cond : float
    A_glass : float

@dataclass
class GeneralHeatpumpParameters:
    buffer_capacitance_kwh : float
    buffer_temp_set : float
    buffer_temp_min : float
    buffer_temp_max : float
    buffer_temp_0 : float
    buffer_temp_hor : float
    house_temp_set : float
    house_temp_min : float
    house_temp_max : float
    house_temp_hor : float
    house_temp_0 : float
    dhw_temp_set : float
    dhw_temp_tap : float

@dataclass
class HybridHeatPumpParameters(GeneralHeatpumpParameters):
    heat_thermal_power_kw : float
    gass_heater_efficiency : float
    gass_heater_thermal_power_kw : float

@dataclass
class HeatPumpParameters(GeneralHeatpumpParameters):
    dhw_capacitance_kwh : float
    heat_element_kw : float
    power_kw : float
    dhw_temperature_set : float
    dhw_temp_set : float
    dhw_temp_min : float
    dhw_temp_max : float
    dhw_temp_0 : float
    dhw_temp_hor : float
    cop_element : float

@dataclass
class EVParameters:
    arrival_ptus : dict[int, float]
    departure_ptus : dict[int, float]
    max_soc_kwh : float
    max_power_kw : float
    efficiency : float
    current_soc_kwh : float
    min_soc_kwh : float
    min_power_kw : float
    min_dep_soc_kwh : float

@dataclass
class BatteryParameters:
    charge_efficiency : float
    discharge_efficiency : float
    max_charge_rate_kw : float
    max_discharge_rate_kw : float
    capacity_kw : float

class EsdlEntityParameterParser:

    def __init__(self):
        self._building_cache : dict[str, BuildingParameters] = {}
        self._hybrid_heatpump_cache : dict[str, HybridHeatPumpParameters] = {}
        self._heatpump_cache : dict[str, HeatPumpParameters] = {}
        self._ev_cache : dict[str, EVParameters] = {}
        self._battery_cache : dict[str, BatteryParameters] = {}
        self._econnection_capacity_cache : dict[str, float] = {}

    def parse_building_data(self, building, building_features, building_info):
        """Extract relevant building and building information properties."""
        building_data = {}
        # Building-level properties
        for feature in building.eClass.eAllStructuralFeatures():
            if feature.name in building_features:
                value = getattr(building, feature.name)
                if value not in [None, 0, 0.0]:
                    building_data[feature.name] = value
        # BuildingInformation properties
        for bi in building.buildinginformation:
            for field in building_info:
                value = getattr(bi, field, None)
                if value not in [None, 0, 0.0]:
                    building_data[field] = value
        # Derived properties
        building_data["roofArea"] = (
                building_data.get("slantedRoofArea", 0)
                + building_data.get("flatRoofArea", 0)
        )
        return building_data

    def get_building_parameters(self, building: esdl.Building) -> BuildingParameters:
        key = building.id
        building_features   = ["buildingYear", "floorArea", "numberOfFloors", "surfaceArea"]
        building_info       = ["slantedRoofArea", "wallArea", "flatRoofArea", "windowArea", "height", "rcWall", "rcRoof",
                                "rcFloor", "uWindow", "doorArea", "uDoor"]
        # Constants house heat calculations
        U_occupants_appliances_W_per_m2  = 5     # [W/m2]
        heatcapacity_air_J_per_m3        = 1230  # [J/m3]
        if key not in self._building_cache:
            building_data = self.parse_building_data(building, building_features, building_info)

            if building_data["buildingYear"] <= 1967:
                qv10 = 4.0  # Air leakage rate at 10 Pa [dm³/s/m²] adopted from the TNO space heating demand model (TNO 2022 P10336, Section 3.3). See README for details and references.
            else:
                qv10 = 0.3 + 3.7 * math.exp((1967 - building_data["buildingYear"]) / 16)  # Air leakage rate at 10 Pa [dm³/s/m²] adopted from the TNO space heating demand model (TNO 2022 P10336, Section 3.3). See README for details and references.
            qv1 = qv10 * (10 ** -0.7)   # Air leakage rate adopted from the TNO space heating demand model (TNO 2022 P10336, Section 3.3). See README for details and references.

            uservolume = building_data["surfaceArea"] * (building_data["height"] / building_data["numberOfFloors"])
            inner_thermal_mass_ratio = 0.22  # Fraction of total building heat capacity assigned to the inner thermal mass adopted from the TNO space heating demand model (TNO 2022 P10336, Section 3.3). See README for details and references.
            C_in = (0.0784 * uservolume + 1.97) * 1e6   # Inner thermal mass heat capacity [J/K] adopted from the TNO space heating demand model (TNO 2022 P10336, Section 3.3). See README for details and references.
            C_out = (C_in / inner_thermal_mass_ratio) * (1 - inner_thermal_mass_ratio) # Outer thermal mass heat capacity [J/K] adopted from the TNO space heating demand model (TNO 2022 P10336, Section 3.3). See README for details and references.

            UA_vent = heatcapacity_air_J_per_m3 * (qv1 * 10 ** -3) * building_data["surfaceArea"]
            UA_exch = U_occupants_appliances_W_per_m2 * building_data["surfaceArea"]
            UA_floor = building_data["floorArea"] / building_data["rcFloor"]
            UA_transm = (building_data["wallArea"] / building_data["rcWall"]) + (
                    (building_data["roofArea"]) / building_data["rcRoof"]) + (
                                building_data["windowArea"] * building_data["uWindow"]) + (
                                building_data["doorArea"] * building_data["uDoor"])
            R_vent = 1 / UA_vent
            R_exch = 1 / UA_exch
            R_floor = 1 / UA_floor
            R_cond = 1 / UA_transm - 1 / UA_exch

            # building_d = json.loads(building.description)
            self._building_cache[key] = BuildingParameters(
                C_in_kwh=C_in / 3.6e6,
                C_out_kwh=C_out / 3.6e6,
                R_exch=R_exch * 1000,
                R_floor=R_floor * 1000,
                R_vent=R_vent * 1000,
                R_cond=R_cond * 1000,
                A_glass=building_data["windowArea"]
            )
        return self._building_cache[key]

    def get_hybridheatpump_parameters(
        self,
        hhp: esdl.HybridHeatPump
    ) -> HybridHeatPumpParameters:
        key = hhp.id
        density_water_kg_per_m3                = 1000  # [kg/m3]
        specific_heat_water_J_per_kg_per_K     = 4183  # [J/(kg K)]
        if key not in self._hybrid_heatpump_cache:
            building = hhp.eContainer()
            for asset in building.asset:
                if isinstance(asset, esdl.WaterBuffer):
                    if "sh_buffer" in asset.name:
                        buffer_volume = asset.volume
                        buffer_capacitance = (buffer_volume * density_water_kg_per_m3 * specific_heat_water_J_per_kg_per_K)
                        buffer_temp_min = celsius_to_kelvin(asset.minStorageTemperature)
                        buffer_temp_max = celsius_to_kelvin(asset.maxStorageTemperature)
                        buffer_temp_set = (buffer_temp_min + buffer_temp_max) / 2
                        heating_demand = next(
                            connected_to.eContainer()
                            for port in asset.port
                            for connected_to in port.connectedTo
                            if isinstance(connected_to.eContainer(), esdl.HeatingDemand))
                        house_temp_min = celsius_to_kelvin(heating_demand.minTemperature)
                        house_temp_max = celsius_to_kelvin(heating_demand.maxTemperature)
            connected_ports = [port for port in hhp.port if len(port.connectedTo) > 0]
            for connected_port in connected_ports:
                for entity in connected_port.connectedTo:
                    if isinstance(entity.eContainer(), esdl.HeatingDemand) and entity.eContainer().type == esdl.HeatDemandTypeEnum.from_string('HOT_TAPWATER'):
                        dhw_temp_set = celsius_to_kelvin(heating_demand.minTemperature)
            self._hybrid_heatpump_cache[key] = HybridHeatPumpParameters(
                buffer_capacitance_kwh=buffer_capacitance / 3.6e6,
                heat_thermal_power_kw=hhp.heatPumpThermalPower * 0.001, # hhp.heatPumpThermalPower
                house_temp_set=house_temp_min,
                house_temp_min=house_temp_min,
                house_temp_max=house_temp_max,
                house_temp_hor=house_temp_min,
                house_temp_0=house_temp_min,
                buffer_temp_set=buffer_temp_set,
                buffer_temp_min=buffer_temp_min,
                buffer_temp_max=buffer_temp_max,
                buffer_temp_0=buffer_temp_set,
                buffer_temp_hor=buffer_temp_set,
                dhw_temp_set=dhw_temp_set,
                dhw_temp_tap=288.15,                                    # 15 degrees C
                gass_heater_efficiency= hhp.gasHeaterEfficiency,
                gass_heater_thermal_power_kw= hhp.gasHeaterThermalPower * 0.001
            )
        return self._hybrid_heatpump_cache[key]

    def get_heatpump_parameters(self, hp: esdl.HeatPump) -> HeatPumpParameters:
        key = hp.id
        density_water_kg_per_m3                = 1000  # [kg/m3]
        specific_heat_water_J_per_kg_per_K     = 4183  # [J/(kg K)]
        if key not in self._heatpump_cache:
            building = hp.eContainer()
            for asset in building.asset:
                if type(asset).__name__ == "WaterBuffer":
                    if "sh_buffer" in asset.name:
                        buffer_volume = asset.volume
                        buffer_capacitance = (buffer_volume * density_water_kg_per_m3 * specific_heat_water_J_per_kg_per_K)
                        buffer_temp_min = celsius_to_kelvin(asset.minStorageTemperature)
                        buffer_temp_max = celsius_to_kelvin(asset.maxStorageTemperature)
                        buffer_temp_set = (buffer_temp_min + buffer_temp_max) / 2
                        heating_demand = next(
                            connected_to.eContainer()
                            for port in asset.port
                            for connected_to in port.connectedTo
                            if isinstance(connected_to.eContainer(), esdl.HeatingDemand))
                        house_temp_min = celsius_to_kelvin(heating_demand.minTemperature)
                        house_temp_max = celsius_to_kelvin(heating_demand.maxTemperature)
                    elif "hw_buffer" in asset.name:
                        dhw_volume = asset.volume
                        dhw_capacitance = (dhw_volume * density_water_kg_per_m3 * specific_heat_water_J_per_kg_per_K)
                        dhw_temp_min = celsius_to_kelvin(asset.minStorageTemperature)
                        dhw_temp_tap = celsius_to_kelvin(asset.minStorageTemperature)
                        heating_demand = next(
                            connected_to.eContainer()
                            for port in asset.port
                            for connected_to in port.connectedTo
                            if isinstance(connected_to.eContainer(), esdl.HeatingDemand)
                        )
                        dhw_temp_set = celsius_to_kelvin(heating_demand.minTemperature)
                        dhw_temp_max = celsius_to_kelvin(heating_demand.maxTemperature)
            self._heatpump_cache[key] = HeatPumpParameters(
                buffer_capacitance_kwh=buffer_capacitance / 3.6e6,
                dhw_capacitance_kwh=dhw_capacitance / 3.6e6,
                heat_element_kw= 3000 * 0.001,                  # check to add to esdl
                power_kw=hp.power * 0.001,
                dhw_temperature_set=dhw_temp_set,
                buffer_temp_set=buffer_temp_set,
                buffer_temp_min=buffer_temp_min,
                buffer_temp_max=buffer_temp_max,
                buffer_temp_0=buffer_temp_set,
                buffer_temp_hor=buffer_temp_set,
                dhw_temp_set=dhw_temp_set,
                dhw_temp_min=dhw_temp_min,
                dhw_temp_max=dhw_temp_max,
                dhw_temp_0=dhw_temp_set,
                dhw_temp_hor=dhw_temp_set,
                dhw_temp_tap=dhw_temp_tap,
                cop_element=hp.COP,
                house_temp_set=house_temp_min,
                house_temp_min=house_temp_min,
                house_temp_max=house_temp_max,
                house_temp_hor=house_temp_min,
                house_temp_0=house_temp_min
            )
        return self._heatpump_cache[key]

    def get_ev_parameters(self, ev : esdl.EVChargingStation, simulation_start_time : datetime, simulation_duration_in_seconds : int, time_step_in_seconds : int, timestep_information : TimeStepInformation) -> EVParameters:
        key = ev.id
        ev_profile_port = next(port for port in ev.port if any(isinstance(connected_to.eContainer(), esdl.MobilityDemand) for connected_to in port.connectedTo))
        mobility_demand : esdl.MobilityDemand = next(obj.eContainer() for obj in ev_profile_port.connectedTo if isinstance(obj.eContainer(), esdl.MobilityDemand))
        profile_port : esdl.OutPort = next(port for port in mobility_demand.port if len(port.profile) > 0)
        datetime_profile : esdl.DateTimeProfile = profile_port.profile[0]
        if key not in self._ev_cache:

            arrival_ptus = {}
            departure_ptus = {}
            current_datetime = simulation_start_time
            end_date_time = simulation_start_time + timedelta(seconds = simulation_duration_in_seconds)
            ev_d = json.loads(ev.description)
            ptu = 1
            min_dep_soc_kwh = 0.8 * ev_d['capacity_kwh']
            while current_datetime <= end_date_time:
                profile_elem_arr = next((elem for elem in datetime_profile.element if current_datetime <= elem.from_ < current_datetime + timedelta(seconds=time_step_in_seconds) and elem.from_ >= simulation_start_time and elem.to <= end_date_time), None)
                profile_elem_dep = next((elem for elem in datetime_profile.element if current_datetime <= elem.to < current_datetime + timedelta(seconds=time_step_in_seconds) and elem.to <= end_date_time and elem.from_ >= simulation_start_time), None)
                if profile_elem_arr is not None:
                    arrival_ptus[ptu] = 0.8 * ev_d['capacity_kwh'] - profile_elem_arr.value
                if profile_elem_dep is not None and len(departure_ptus) == len(arrival_ptus) - 1:
                    last_key = next(reversed(arrival_ptus), None)
                    arrival_date = simulation_start_time + timedelta(seconds = last_key * time_step_in_seconds)
                    departure_date = current_datetime + timedelta(seconds=time_step_in_seconds)
                    time_delta_dep_arr = departure_date - arrival_date
                    max_to_charge_in_time = (ev.power * 0.001 * 1/3600) * time_delta_dep_arr.seconds * ev_d['efficiency']
                    if max_to_charge_in_time > profile_elem_dep.value:
                        departure_ptus[ptu] = min_dep_soc_kwh
                    else:
                        arrival_ptus.pop(last_key)
                ptu += 1
                current_datetime = current_datetime + timedelta(seconds=time_step_in_seconds)

            self._filter_out_consecutive_loading_sessions(arrival_ptus, departure_ptus)

            self._ev_cache[key] = EVParameters(
                arrival_ptus=arrival_ptus,
                departure_ptus=departure_ptus,
                max_soc_kwh=ev_d['capacity_kwh'],
                max_power_kw=ev.power * 0.001,
                efficiency = ev_d['efficiency'],
                current_soc_kwh=0,
                min_soc_kwh=ev_d['min_soc_percentage_v2g'] * ev_d['capacity_kwh'],
                min_power_kw=ev_d['min_charge_rate_kw'],
                min_dep_soc_kwh=min_dep_soc_kwh
            )

        ev_params = self._ev_cache[key]
        eps = 1.0e-3
        if timestep_information.current_time_step_number + 1 in ev_params.arrival_ptus:
            ev_params.current_soc_kwh = ev_params.arrival_ptus[timestep_information.current_time_step_number + 1]
        elif timestep_information.current_time_step_number - 1 in ev_params.departure_ptus or -eps < ev_params.current_soc_kwh < 0:
            ev_params.current_soc_kwh = 0
            ev_params.min_soc_kwh = 0
        return ev_params

    def _filter_out_consecutive_loading_sessions(self, arrival_ptus, departure_ptus):
        dep_ptus = list(departure_ptus.keys())
        arr_ptus = list(arrival_ptus.keys())
        if len(arr_ptus) > 1 and len(dep_ptus) > 1:
            arr_ptus_to_iterate = arr_ptus[1:]
            dep_ptus_to_iterate = dep_ptus[1:]
            prev_dep_ptu = dep_ptus[0]
            for arr_ptu, dep_ptu in zip(arr_ptus_to_iterate, dep_ptus_to_iterate):
                if arr_ptu - prev_dep_ptu <= 2:
                    arrival_ptus.pop(arr_ptu)
                    departure_ptus.pop(dep_ptu)
                else:
                    prev_dep_ptu = dep_ptu

    def set_soc_ev(self, ev_charginstation : esdl.EVChargingStation, soc_ev : float):
        self._ev_cache[ev_charginstation.id].current_soc_kwh = soc_ev

    def get_battery_parameters(self, battery: esdl.Battery) -> BatteryParameters:
        key = battery.id
        if key not in self._battery_cache:
            self._battery_cache[key] = BatteryParameters(
                charge_efficiency=battery.chargeEfficiency,
                discharge_efficiency=battery.dischargeEfficiency,
                max_charge_rate_kw=battery.maxChargeRate * 0.001,
                max_discharge_rate_kw=battery.maxDischargeRate * 0.001,
                capacity_kw=battery.capacity / 3.6e6
            )
        return self._battery_cache[key]
    
    def get_capacity_from_econnection(self, econnection: esdl.EConnection) -> float:
        key = econnection.id
        if key not in self._econnection_capacity_cache:
            self._econnection_capacity_cache[key] = econnection.capacity * 0.001 if econnection.capacity > 0 else 17.0
        return self._econnection_capacity_cache[key]