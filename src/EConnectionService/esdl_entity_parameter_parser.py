import json
from typing import List
import esdl
from dataclasses import dataclass

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
    arrival_socs_kwh : List[float]
    departure_socs_kwh : List[float]
    arrival_ptus : List[int]
    departure_ptus : List[int]
    max_soc_kwh : float
    max_power_kw : float
    efficiency : float

class EsdlEntityParameterParser:

    @staticmethod
    def get_building_parameters(building : esdl.Building) -> BuildingParameters:
        building_d = json.loads(building.description)
        return BuildingParameters(
            C_in_kwh=building_d['C_in'] * 1/3.6e6,
            C_out_kwh=building_d['C_out'] * 1/3.6e6,
            R_exch=building_d['R_exch'] * 1000,
            R_floor=building_d['R_floor'] * 1000,
            R_vent=building_d['R_vent'] * 1000,
            R_cond=building_d['R_cond'] * 1000,
            A_glass=building_d['A_glass']
        )

    @staticmethod
    def get_hybridheatpump_parameters(hhp : esdl.HybridHeatPump) -> HybridHeatPumpParameters:
        hhp_d = json.loads(hhp.description)
        return HybridHeatPumpParameters(
            buffer_capacitance_kwh=hhp_d['buffer_capacitance'] * 1/3.6e6,
            heat_thermal_power_kw = hhp.heatPumpThermalPower * 0.001,
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

    @staticmethod
    def get_heatpump_parameters(hp : esdl.HeatPump) -> HeatPumpParameters:
        hp_d = json.loads(hp.description)
        return HeatPumpParameters(
            buffer_capacitance_kwh=hp_d['buffer_capacitance'] * 1/3.6e6,
            dhw_capacitance_kwh=hp_d['dhw_capacitance'] * 1/3.6e6,
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

    @staticmethod
    def get_ev_parameters(ev : esdl.EVChargingStation) -> EVParameters:
        ev_d = json.loads(ev.description)
        arrival_socs = ev_d['arrival_socs']
        departure_socs = ev_d['departure_socs']
        arrival_socs = [arrival_soc * 1/3.6e6 for arrival_soc in arrival_socs]
        departure_socs = [departure_soc * 1/3.6e6 for departure_soc in departure_socs]
        return EVParameters(
            arrival_socs_kwh=arrival_socs,
            departure_socs_kwh=departure_socs,
            arrival_ptus=ev_d['arrival_ptus'],
            departure_ptus=ev_d['departure_ptus'],
            max_soc_kwh=ev_d['max_soc']  * 1/3.6e6,
            max_power_kw=ev.power * 0.001,
            efficiency = ev_d['efficiency'],
        )
    
    @staticmethod
    def get_capacity_from_econnection(econnection : esdl.EConnection) -> float:
        return econnection.capacity * 0.001