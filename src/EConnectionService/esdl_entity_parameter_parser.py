from datetime import datetime, timedelta
import json
from typing import List
import esdl
from dataclasses import dataclass

from dots_infrastructure.DataClasses import TimeStepInformation

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

@dataclass
class HybridHeatPumpParameters(GeneralHeatpumpParameters):
    heat_thermal_power_kw : float

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
    dhw_temp_tap : float
    cop_element : float

@dataclass
class EVParameters:
    arrival_ptus : List[int]
    departure_ptus : List[int]
    max_soc_kwh : float
    max_power_kw : float
    efficiency : float
    current_soc_kwh : float

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

    def get_building_parameters(self, building: esdl.Building) -> BuildingParameters:
        key = id(building)
        if key not in self._building_cache:
            building_d = json.loads(building.description)
            self._building_cache[key] = BuildingParameters(
                C_in_kwh=building_d['C_in'] / 3.6e6,
                C_out_kwh=building_d['C_out'] / 3.6e6,
                R_exch=building_d['R_exch'] * 1000,
                R_floor=building_d['R_floor'] * 1000,
                R_vent=building_d['R_vent'] * 1000,
                R_cond=building_d['R_cond'] * 1000,
                A_glass=building_d['A_glass']
            )
        return self._building_cache[key]

    def get_hybridheatpump_parameters(
        self,
        hhp: esdl.HybridHeatPump
    ) -> HybridHeatPumpParameters:
        key = hhp.id
        if key not in self._hybrid_heatpump_cache:
            hhp_d = json.loads(hhp.description)
            self._hybrid_heatpump_cache[key] = HybridHeatPumpParameters(
                buffer_capacitance_kwh=hhp_d['buffer_capacitance'] / 3.6e6,
                heat_thermal_power_kw=hhp.heatPumpThermalPower * 0.001,
                house_temp_set=hhp_d['house_temp_set'],
                house_temp_min=hhp_d['house_temp_min'],
                house_temp_max=hhp_d['house_temp_max'],
                house_temp_hor=hhp_d['house_temp_hor'],
                house_temp_0=hhp_d['house_temp_0'],
                buffer_temp_set=hhp_d['buffer_temp_set'],
                buffer_temp_min=hhp_d['buffer_temp_min'],
                buffer_temp_max=hhp_d['buffer_temp_max'],
                buffer_temp_0=hhp_d['buffer_temp_0'],
                buffer_temp_hor=hhp_d['buffer_temp_hor']
            )
        return self._hybrid_heatpump_cache[key]

    def get_heatpump_parameters(self, hp: esdl.HeatPump) -> HeatPumpParameters:
        key = hp.id
        if key not in self._heatpump_cache:
            hp_d = json.loads(hp.description)
            self._heatpump_cache[key] = HeatPumpParameters(
                buffer_capacitance_kwh=hp_d['buffer_capacitance'] / 3.6e6,
                dhw_capacitance_kwh=hp_d['dhw_capacitance'] / 3.6e6,
                heat_element_kw=hp_d['heat_element'] * 0.001,
                power_kw=hp.power * 0.001,
                dhw_temperature_set=hp_d['dhw_temp_set'],
                buffer_temp_set=hp_d['buffer_temp_set'],
                buffer_temp_min=hp_d['buffer_temp_min'],
                buffer_temp_max=hp_d['buffer_temp_max'],
                buffer_temp_0=hp_d['buffer_temp_0'],
                buffer_temp_hor=hp_d['buffer_temp_hor'],
                dhw_temp_set=hp_d['dhw_temp_set'],
                dhw_temp_min=hp_d['dhw_temp_min'],
                dhw_temp_max=hp_d['dhw_temp_max'],
                dhw_temp_0=hp_d['dhw_temp_0'],
                dhw_temp_hor=hp_d['dhw_temp_hor'],
                dhw_temp_tap=hp_d['dhw_temp_tap'],
                cop_element=hp_d['cop_element'],
                house_temp_set=hp_d['house_temp_set'],
                house_temp_min=hp_d['house_temp_min'],
                house_temp_max=hp_d['house_temp_max'],
                house_temp_hor=hp_d['house_temp_hor'],
                house_temp_0=hp_d['house_temp_0']
            )
        return self._heatpump_cache[key]

    def get_ev_parameters(self, ev : esdl.EVChargingStation, simulation_start_time : datetime, simulation_duration_in_seconds : int, time_step_in_seconds : int, current_simulation_time : datetime) -> EVParameters:
        key = ev.id
        ev_profile_port = next(port for port in ev.port if any(isinstance(connected_to.eContainer(), esdl.MobilityDemand) for connected_to in port.connectedTo))
        mobility_demand : esdl.MobilityDemand = next(obj.eContainer() for obj in ev_profile_port.connectedTo if isinstance(obj.eContainer(), esdl.MobilityDemand))
        profile_port : esdl.OutPort = next(port for port in mobility_demand.port if len(port.profile) > 0)
        datetime_profile : esdl.DateTimeProfile = profile_port.profile[0]
        if key not in self._ev_cache:

            arrival_ptus = []
            departure_ptus = []
            current_datetime = simulation_start_time
            end_date_time = simulation_start_time + timedelta(seconds = simulation_duration_in_seconds)
            ptu = 0
            while current_datetime <= end_date_time:
                arrival_ptu = any(elem.from_ for elem in datetime_profile.element if current_datetime <= elem.from_ < current_datetime + timedelta(seconds=time_step_in_seconds) )
                departure_ptu = any(elem.to for elem in datetime_profile.element if current_datetime <= elem.to < current_datetime + timedelta(seconds=time_step_in_seconds) )
                if arrival_ptu:
                    arrival_ptus.append(ptu)
                if departure_ptu and len(departure_ptus) == len(arrival_ptus) - 1:
                    departure_ptus.append(ptu)
                ptu += 1
                current_datetime = current_datetime + timedelta(seconds=time_step_in_seconds)

            ev_d = json.loads(ev.description)

            self._ev_cache[key] = EVParameters(
                arrival_ptus=arrival_ptus,
                departure_ptus=departure_ptus,
                max_soc_kwh=0,
                max_power_kw=ev.power * 0.001,
                efficiency = ev_d['efficiency'],
                current_soc_kwh=0
            )

        active_profile_elem = next((profile_elem for profile_elem in datetime_profile.element if profile_elem.from_ <= current_simulation_time <= profile_elem.to), None)
        max_soc_kwh = 0
        if active_profile_elem is not None:
            max_soc_kwh = active_profile_elem.value

        ev_params = self._ev_cache[key]
        ev_params.max_soc_kwh = max_soc_kwh
        return ev_params

    def set_soc_ev(self, ev_charginstation : esdl.EVChargingStation, current_soc_kwh : float):
        self._ev_cache[ev_charginstation.id].current_soc_kwh = current_soc_kwh

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
            self._econnection_capacity_cache[key] = econnection.capacity * 0.001
        return self._econnection_capacity_cache[key]