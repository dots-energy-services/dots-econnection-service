import esdl
import pyomo.environ as pyo
import numpy as np
from pyomo.opt import SolverFactory
from dots_infrastructure.Logger import LOGGER
from pyomo.core.base.var import IndexedVar, ScalarVar
from pyomo.core.base.param import IndexedParam, ScalarParam
import json
import copy


class PortfolioOptimizationProblem:
    def __init__(self):
        self.model = pyo.ConcreteModel()
        self.has_heat_pump = False

    def create_time(self, time_params: dict):
        self.model.time_index_p = pyo.RangeSet(0, time_params['n_steps'] - 1)
        self.model.time_index_soc = pyo.RangeSet(0, time_params['n_steps'])
        self.model.dt = pyo.Param(initialize=time_params['dt'])
        self.model.time_step_nr = pyo.Param(initialize=time_params['time_step_nr'])

    def create_electricity_demand(self, active_power: list):
        # Parameters
        p_edemand_dict = self.it2dict(active_power)
        self.model.p_edemand = pyo.Param(self.model.time_index_p, within=pyo.Reals, initialize=p_edemand_dict)

    def create_ev_charging_station(self, ev_charging_station: esdl.EVChargingStation, state_of_charge: float):
        # change arrival/departure ptus based on current simulated time-step
        # e.g. we work in relative ptus from the current simulated ptu
        ev_d = copy.deepcopy(json.loads(ev_charging_station.description))
        time_step_nr = pyo.value(self.model.time_step_nr)
        arrival_ptus = [ptu - (time_step_nr - 1) for ptu in ev_d['arrival_ptus']]  # first simulated time step is 1
        departure_ptus = [ptu - (time_step_nr - 1) for ptu in ev_d['departure_ptus']]

        # Parameters
        # Numbers
        self.model.capacity_ev = pyo.Param(within=pyo.NonNegativeReals, initialize=ev_d['max_soc'])
        self.model.init_soc_ev = pyo.Param(within=pyo.NonNegativeReals, initialize=state_of_charge)

        self.model.ch_eff_ev = pyo.Param(within=pyo.NonNegativeReals, initialize=ev_d['efficiency'])
        self.model.max_ch_rate_ev = pyo.Param(within=pyo.NonNegativeReals, initialize=ev_charging_station.power)

        # Arrays
        # Create availability list
        number_of_ptus = len(self.model.time_index_p)
        availability_ev = number_of_ptus * [0]
        for arrival_ptu, departure_ptu in zip(arrival_ptus, departure_ptus):
            # Add 1 to departure, because by convention the car can be charged during the departure ptu
            for ptu in range(max(0, arrival_ptu), max(0, min(departure_ptu, number_of_ptus))):
                availability_ev[ptu] = 1
        self.model.availability_ev = pyo.Param(self.model.time_index_p, within=pyo.Binary,
                                               initialize=self.it2dict(availability_ev))

        # Variables
        self.model.p_ev = pyo.Var(self.model.time_index_p, within=pyo.NonNegativeReals, initialize=0)
        self.model.soc_ev = pyo.Var(self.model.time_index_soc, within=pyo.NonNegativeReals,
                                    initialize=self.model.init_soc_ev)

        self.model.con_ev_ch_limit = pyo.Constraint(
            self.model.time_index_p, rule=lambda m, t:
            m.p_ev[t] <= m.availability_ev[t] * m.max_ch_rate_ev  # is 0 if the car is not there
        )

        self.model.con_soc_ev_min = pyo.Constraint(
            self.model.time_index_soc, rule=lambda m, t:
            m.soc_ev[t] >= 0.0
        )

        self.model.con_soc_ev_max = pyo.Constraint(
            self.model.time_index_soc, rule=lambda m, t:
            m.soc_ev[t] <= m.capacity_ev
        )

        self.model.con_soc_ev_init = pyo.Constraint(
            self.model.time_index_soc, rule=lambda m, t:
            m.soc_ev[m.time_index_soc.first()] == m.init_soc_ev
        )

        def arrival_constraint_f(model, t):
            if t in arrival_ptus:
                session_nr = arrival_ptus.index(t)
                arrival_soc = ev_d['arrival_socs'][session_nr]
                return model.soc_ev[t] == arrival_soc
            else:
                return pyo.Constraint.Skip

        self.model.con_soc_ev_arr = pyo.Constraint(self.model.time_index_soc, rule=arrival_constraint_f)

        def departure_constraint_f(model, t):
            if t in departure_ptus:
                session_nr = departure_ptus.index(t)
                departure_soc = ev_d['departure_socs'][session_nr]
                return model.soc_ev[t] >= departure_soc
            else:
                return pyo.Constraint.Skip

        self.model.con_soc_ev_dep = pyo.Constraint(self.model.time_index_soc, rule=departure_constraint_f)

        def soc_update_f(model, t):
            if (any(arr_ptu <= t < dep_ptu for arr_ptu, dep_ptu in
                    zip(arrival_ptus, departure_ptus))) \
                    and (t < model.time_index_soc.last()):
                return model.soc_ev[t + 1] == model.soc_ev[t] + model.p_ev[t] * model.dt  # m.ch_eff_ev
            else:
                return pyo.Constraint.Skip

        self.model.con_soc_ev_update = pyo.Constraint(self.model.time_index_soc, rule=soc_update_f)

    def create_pv(self, potential_active_power: list):
        # Parameters
        potential_p_pv_dict = self.it2dict(potential_active_power)
        LOGGER.debug(f"Potential PV dict: {potential_p_pv_dict}")
        self.model.p_pv_max = pyo.Param(self.model.time_index_p, within=pyo.NonNegativeReals, initialize=potential_p_pv_dict)

        # Variables
        self.model.p_pv_use = pyo.Var(self.model.time_index_p, within=pyo.NonNegativeReals, initialize=0)
        self.model.p_pv_sell = pyo.Var(self.model.time_index_p, within=pyo.NonNegativeReals, initialize=0)

        # Constraints
        self.model.con_pv_limit = pyo.Constraint(
            self.model.time_index_p, rule=lambda m, t:
            m.p_pv_use[t] + m.p_pv_sell[t] <= m.p_pv_max[t]
        )

    def create_battery(self, battery: esdl.Battery, state_of_charge: float):
        # Parameters
        self.model.capacity = pyo.Param(within=pyo.NonNegativeReals, initialize=battery.capacity)
        self.model.init_soc = pyo.Param(within=pyo.NonNegativeReals, initialize=state_of_charge)

        self.model.hor_soc = pyo.Param(within=pyo.NonNegativeReals, initialize=0.5 * battery.capacity)
        self.model.ch_eff = pyo.Param(within=pyo.NonNegativeReals, initialize=battery.chargeEfficiency)
        self.model.max_ch_rate = pyo.Param(within=pyo.NonNegativeReals, initialize=battery.maxChargeRate)

        # Variables
        # eta * p_dch == p_bat_use + p_bat_sell
        self.model.p_ch = pyo.Var(self.model.time_index_p, within=pyo.NonNegativeReals, initialize=0)
        self.model.p_bat_use = pyo.Var(self.model.time_index_p, within=pyo.NonNegativeReals, initialize=0)
        self.model.p_bat_sell = pyo.Var(self.model.time_index_p, within=pyo.NonNegativeReals, initialize=0)
        self.model.z_ch = pyo.Var(self.model.time_index_p, within=pyo.Binary, initialize=0)
        self.model.soc = pyo.Var(self.model.time_index_soc, within=pyo.NonNegativeReals, initialize=self.model.init_soc)

        self.model.con_bat_ch_limit = pyo.Constraint(
            self.model.time_index_p, rule=lambda m, t:
            m.p_ch[t] <= m.z_ch[t] * m.max_ch_rate
        )

        self.model.con_bat_dch_limit = pyo.Constraint(
            self.model.time_index_p, rule=lambda m, t:
            1 / m.ch_eff * (m.p_bat_use[t] + m.p_bat_sell[t]) <= (1 - m.z_ch[t]) * m.max_ch_rate
        )

        self.model.con_soc_min = pyo.Constraint(
            self.model.time_index_soc, rule=lambda m, t:
            m.soc[t] >= 0.0
        )

        self.model.con_soc_max = pyo.Constraint(
            self.model.time_index_soc, rule=lambda m, t:
            m.soc[t] <= m.capacity
        )

        self.model.con_soc_init = pyo.Constraint(
            self.model.time_index_soc, rule=lambda m, t:
            m.soc[m.time_index_soc.first()] == m.init_soc
        )

        self.model.con_soc_hor = pyo.Constraint(
            self.model.time_index_soc, rule=lambda m, t:
            m.soc[m.time_index_soc.last()] >= m.hor_soc
        )

        self.model.con_soc_update = pyo.Constraint(
            self.model.time_index_soc, rule=lambda m, t:
            m.soc[t + 1] == m.soc[t] + (m.ch_eff * m.p_ch[t] - 1 / m.ch_eff * (m.p_bat_use[t] + m.p_bat_sell[t])) * m.dt
            if t < m.time_index_soc.last() else pyo.Constraint.Skip
        )

    def create_heat_pump(self,
                         heat_pump: esdl.HeatPump,
                         dhw_temperature: float,
                         buffer_temperature: float,
                         house_temperatures: list,
                         air_temperature: list,
                         soil_temperature: list,
                         solar_irradiance: list,
                         dhw_profile: list):

        air_temperature_dict = self.it2dict(air_temperature)
        soil_temperature_dict = self.it2dict(soil_temperature)
        solar_irradiance_dict = self.it2dict(solar_irradiance)

        # Parameters
        # Weather
        self.model.T_air = pyo.Param(self.model.time_index_p, within=pyo.NonNegativeReals, initialize=air_temperature_dict)
        self.model.T_soil = pyo.Param(self.model.time_index_p, within=pyo.NonNegativeReals, initialize=soil_temperature_dict)
        self.model.I_sol = pyo.Param(self.model.time_index_p, within=pyo.NonNegativeReals, initialize=solar_irradiance_dict)

        # House
        # Create capacitance and conductance matrices
        building = heat_pump.eContainer()
        building_d = json.loads(building.description)
        heat_pump_d = json.loads(heat_pump.description)

        capacitance_matrix = np.diag(np.array([building_d['C_in'], building_d['C_out']]))

        k_exch = 1.0 / building_d['R_exch']
        k_floor = 1.0 / building_d['R_floor']
        k_vent = 1.0 / building_d['R_vent']
        k_cond = 1.0 / building_d['R_cond']

        conductance_matrix = np.array([[k_vent + k_exch + k_floor, -k_exch], [-k_exch, k_cond + k_exch]])
        conductance_matrix_amb = np.array([[k_vent, k_floor], [k_cond, 0]])

        # Convert L/s for dhw profile to power using the heat capacity of water and the temperature difference
        dhw_heat_profile = np.array(dhw_profile) * 4183 * (heat_pump_d['dhw_temp_set'] - heat_pump_d['dhw_temp_tap'])
        dhw_heat_profile_dict = self.it2dict(dhw_heat_profile)

        # Parameters
        # DHW
        self.model.Q_to_dhw = pyo.Param(self.model.time_index_p, within=pyo.NonNegativeReals, initialize=dhw_heat_profile_dict)

        mat_index = pyo.RangeSet(1, len(capacitance_matrix))
        self.model.C_house = pyo.Param(mat_index, mat_index, initialize=self.mat2dict(capacitance_matrix))
        self.model.K_house = pyo.Param(mat_index, mat_index, initialize=self.mat2dict(conductance_matrix))
        self.model.K_house_amb = pyo.Param(mat_index, mat_index, initialize=self.mat2dict(conductance_matrix_amb))
        self.model.window_area = pyo.Param(initialize=building_d['A_glass'])

        # Heat pump
        self.model.Q_nom = pyo.Param(within=pyo.NonNegativeReals, initialize=heat_pump.power)
        self.model.min_rel_heat = pyo.Param(within=pyo.NonNegativeReals, initialize=0.3)
        self.model.C_dhw = pyo.Param(within=pyo.NonNegativeReals, initialize=heat_pump_d['dhw_capacitance'])
        self.model.C_buffer = pyo.Param(within=pyo.NonNegativeReals, initialize=heat_pump_d['buffer_capacitance'])
        self.model.T_dhw_min = pyo.Param(within=pyo.NonNegativeReals, initialize=heat_pump_d['dhw_temp_min'])
        self.model.T_dhw_max = pyo.Param(within=pyo.NonNegativeReals, initialize=heat_pump_d['buffer_temp_max'])
        self.model.T_dhw_hor = pyo.Param(within=pyo.NonNegativeReals, initialize=heat_pump_d['dhw_temp_hor'])
        self.model.T_buffer_min = pyo.Param(within=pyo.NonNegativeReals, initialize=heat_pump_d['buffer_temp_min'])
        self.model.T_buffer_max = pyo.Param(within=pyo.NonNegativeReals, initialize=heat_pump_d['buffer_temp_max'])
        self.model.T_buffer_hor = pyo.Param(within=pyo.NonNegativeReals, initialize=heat_pump_d['buffer_temp_hor'])
        self.model.T_house_min = pyo.Param(within=pyo.NonNegativeReals, initialize=heat_pump_d['house_temp_min'])
        self.model.T_house_max = pyo.Param(within=pyo.NonNegativeReals, initialize=heat_pump_d['house_temp_max'])
        self.model.T_house_hor = pyo.Param(within=pyo.NonNegativeReals, initialize=heat_pump_d['house_temp_hor'])
        self.model.Q_element = pyo.Param(within=pyo.NonNegativeReals, initialize=heat_pump_d['heat_element'])
        self.model.COP_element = pyo.Param(within=pyo.NonNegativeReals, initialize=heat_pump_d['cop_element'])

        # Take simplified approach to cops
        self.model.COP_sh = pyo.Param(initialize=4.0, within=pyo.NonNegativeReals)  # [-]
        self.model.COP_dhw = pyo.Param(initialize=2.5, within=pyo.NonNegativeReals)  # [-]

        # initial values from input
        self.model.T_in_0 = pyo.Param(initialize=house_temperatures[0])
        self.model.T_out_0 = pyo.Param(initialize=house_temperatures[1])
        self.model.T_dhw_0 = pyo.Param(initialize=dhw_temperature)
        self.model.T_buffer_0 = pyo.Param(initialize=buffer_temperature)

        # Variables
        # Powers
        self.model.Q_to_dhw_tank = pyo.Var(self.model.time_index_p, within=pyo.NonNegativeReals, initialize=0)
        self.model.Q_to_buffer = pyo.Var(self.model.time_index_p, within=pyo.NonNegativeReals, initialize=0)
        self.model.Q_to_house = pyo.Var(self.model.time_index_p, within=pyo.NonNegativeReals, initialize=0)
        self.model.p_hp = pyo.Var(self.model.time_index_p, within=pyo.NonNegativeReals, initialize=0)
        self.model.z_on_sh = pyo.Var(self.model.time_index_p, within=pyo.Binary, initialize=0)
        self.model.z_on_dhw = pyo.Var(self.model.time_index_p, within=pyo.Binary, initialize=0)
        self.model.z_element_on = pyo.Var(self.model.time_index_p, within=pyo.Binary, initialize=0)

        # Temperatures
        self.model.T_dhw = pyo.Var(self.model.time_index_soc, within=pyo.NonNegativeReals,
                                   initialize=self.model.T_dhw_0)
        self.model.T_buffer = pyo.Var(self.model.time_index_soc, within=pyo.NonNegativeReals,
                                      initialize=self.model.T_buffer_0)
        self.model.T_in = pyo.Var(self.model.time_index_soc, within=pyo.NonNegativeReals, initialize=self.model.T_in_0)
        self.model.T_out = pyo.Var(self.model.time_index_soc, within=pyo.NonNegativeReals,
                                   initialize=self.model.T_out_0)
        self.model.slack_soc_max = pyo.Param(self.model.time_index_soc, within=pyo.NonNegativeReals, initialize=0)
        self.model.slack_soc_min = pyo.Param(self.model.time_index_soc, within=pyo.NonNegativeReals, initialize=0)

        # Constraints
        self.model.con_hp_ch_min_dhw = pyo.Constraint(
            self.model.time_index_p, rule=lambda m, t:
            m.Q_to_dhw_tank[t] >= m.z_on_dhw[t] * m.min_rel_heat * m.Q_nom
        )

        self.model.con_hp_ch_max_dhw = pyo.Constraint(
            self.model.time_index_p, rule=lambda m, t:
            m.Q_to_dhw_tank[t] <= m.z_on_dhw[t] * m.Q_nom
        )

        self.model.con_hp_ch_min = pyo.Constraint(
            self.model.time_index_p, rule=lambda m, t:
            m.Q_to_buffer[t] >= m.z_on_sh[t] * m.min_rel_heat * m.Q_nom
        )

        self.model.con_hp_ch_max = pyo.Constraint(
            self.model.time_index_p, rule=lambda m, t:
            m.Q_to_buffer[t] <= m.z_on_sh[t] * m.Q_nom
        )

        self.model.con_on = pyo.Constraint(
            self.model.time_index_p, rule=lambda m, t:
            m.z_on_sh[t] + m.z_on_dhw[t] <= 1
        )

        self.model.con_dhw_temp_min = pyo.Constraint(
            self.model.time_index_soc, rule=lambda m, t:
            m.T_dhw[t] >= m.T_dhw_min
        )

        self.model.con_buffer_temp_min = pyo.Constraint(
            self.model.time_index_soc, rule=lambda m, t:
            m.T_buffer[t] >= m.T_buffer_min
        )

        self.model.con_house_temp_min = pyo.Constraint(
            self.model.time_index_soc, rule=lambda m, t:
            m.T_in[t] >= m.T_house_min - m.slack_soc_min[t]
        )

        self.model.con_dhw_temp_max = pyo.Constraint(
            self.model.time_index_soc, rule=lambda m, t:
            m.T_dhw[t] <= m.T_dhw_max
        )

        self.model.con_buffer_temp_max = pyo.Constraint(
            self.model.time_index_soc, rule=lambda m, t:
            m.T_buffer[t] <= m.T_buffer_max
        )

        '''
        # pyo.Constraints for not heating house over maximum temperature
        self.model.con_heat_to_house_z = pyo.Constraint(
            self.model.time_index_soc, rule=lambda m, t:
            (m.T_i[t] - m.T_house_max) <= 1.0e5 * m.z_upper_bound[t]
        )

        # Q cannot cause (hence t+1) T to go above the uppper bound
        self.model.con_heat_to_house_q = pyo.Constraint(
            self.model.time_index_p, rule=lambda m, t:
            m.Q_to_house[t] <= (1 - m.z_upper_bound[t + 1]) * m.C_buffer * (m.T_buffer_max - m.T_buffer_min)/m.dt
        )
        '''
        if not self.exceed_upper_temp_house_2(heat_pump, house_temperatures, air_temperature, soil_temperature,
                                              solar_irradiance, capacitance_matrix, conductance_matrix,
                                              conductance_matrix_amb):

            LOGGER.info("Upper temperature bound house imposed")
            self.model.con_house_temp_max = pyo.Constraint(
                self.model.time_index_soc, rule=lambda m, t:
                m.T_in[t] <= m.T_house_max + m.slack_soc_max[t]
            )
        else:
            LOGGER.info("Upper temperature bound house NOT imposed")
            # set slack_soc_max as an param to 0 to increase stability of the solver
            self.model.slack_soc_max = pyo.Param(self.model.time_index_soc, within=pyo.NonNegativeReals, initialize=0)
        # '''

        # Initial Conditions
        self.model.con_dhw_temp_init = pyo.Constraint(rule=lambda m: m.T_dhw[m.time_index_soc.first()] == m.T_dhw_0)
        self.model.con_buffer_temp_init = pyo.Constraint(
            rule=lambda m: m.T_buffer[m.time_index_soc.first()] == m.T_buffer_0)
        self.model.cnstr_T_in0 = pyo.Constraint(rule=lambda m: m.T_in[self.model.time_index_soc.first()] == m.T_in_0)
        self.model.cnstr_T_out0 = pyo.Constraint(rule=lambda m: m.T_out[self.model.time_index_soc.first()] == m.T_out_0)

        # Final Conditions
        self.model.con_dhw_temp_hor = pyo.Constraint(rule=lambda m: m.T_dhw[m.time_index_soc.last()] >= m.T_dhw_hor)
        self.model.con_buffer_temp_hor = pyo.Constraint(
            rule=lambda m: m.T_buffer[m.time_index_soc.last()] >= m.T_buffer_hor)
        self.model.con_house_temp_hor = pyo.Constraint(rule=lambda m: m.T_in[m.time_index_soc.last()] >= m.T_house_hor)

        # update temperatures
        self.model.con_dhw_temp_update = pyo.Constraint(
            self.model.time_index_soc, rule=lambda m, t:
            m.C_dhw * m.T_dhw[t + 1] == m.C_dhw * m.T_dhw[t] + (
                    m.Q_to_dhw_tank[t] - m.Q_to_dhw[t] + m.z_element_on[t] * m.Q_element) * m.dt
            if t < m.time_index_soc.last() else pyo.Constraint.Skip
        )

        self.model.con_buffer_temp_update = pyo.Constraint(
            self.model.time_index_soc, rule=lambda m, t:
            m.C_buffer * m.T_buffer[t + 1] == m.C_buffer * m.T_buffer[t] + (
                    m.Q_to_buffer[t] - m.Q_to_house[t]) * m.dt
            if t < m.time_index_soc.last() else pyo.Constraint.Skip
        )

        def constraint_update_T_in(m, t):
            KT = m.K_house[1, 1] * m.T_in[t] + m.K_house[1, 2] * m.T_out[t]
            KT_amb = m.K_house_amb[1, 1] * m.T_air[t] + m.K_house_amb[1, 2] * m.T_soil[t]
            solar = m.window_area * m.I_sol[t]
            hp = m.Q_to_house[t]

            return (m.C_house[1, 1] * m.T_in[t + 1] == m.C_house[1, 1] * m.T_in[t] + m.dt *
                    (-KT + KT_amb + solar + hp))

        def constraint_update_T_out(m, t):
            KT = m.K_house[2, 1] * m.T_in[t] + m.K_house[2, 2] * m.T_out[t]
            KT_amb = m.K_house_amb[2, 1] * m.T_air[t] + m.K_house_amb[2, 2] * m.T_soil[t]
            solar = 0.0
            hp = 0.0
            constraint = (m.C_house[2, 2] * m.T_out[t + 1] == m.C_house[2, 2] * m.T_out[t] + m.dt *
                          (-KT + KT_amb + solar + hp))
            return constraint

        self.model.con_update_T_in = pyo.Constraint(self.model.time_index_p, rule=constraint_update_T_in)
        self.model.con_update_T_out = pyo.Constraint(self.model.time_index_p, rule=constraint_update_T_out)

        # definition pyo.Constraint
        self.model.con_P = pyo.Constraint(
            self.model.time_index_p, rule=lambda m, t:
            m.Q_to_buffer[t] / m.COP_sh + m.Q_to_dhw_tank[t] / m.COP_dhw + m.z_element_on[
                t] * m.Q_element / m.COP_element == m.p_hp[t]
        )
        self.has_heat_pump = True

    def create_hybrid_heat_pump(self,
                                hybrid_heat_pump: esdl.HybridHeatPump,
                                buffer_temperature: float,
                                house_temperatures: list,
                                air_temperature: list,
                                soil_temperature: list,
                                solar_irradiance: list):

        air_temperature_dict = self.it2dict(air_temperature)
        soil_temperature_dict = self.it2dict(soil_temperature)
        solar_irradiance_dict = self.it2dict(solar_irradiance)

        # Parameters
        # Weather
        self.model.T_air = pyo.Param(self.model.time_index_p, within=pyo.NonNegativeReals, initialize=air_temperature_dict)
        self.model.T_soil = pyo.Param(self.model.time_index_p, within=pyo.NonNegativeReals, initialize=soil_temperature_dict)
        self.model.I_sol = pyo.Param(self.model.time_index_p, within=pyo.NonNegativeReals, initialize=solar_irradiance_dict)

        # House
        # Create capacitance and conductance matrices
        building = hybrid_heat_pump.eContainer()
        building_d = json.loads(building.description)
        hybrid_heat_pump_d = json.loads(hybrid_heat_pump.description)

        capacitance_matrix = np.diag(np.array([building_d['C_in'], building_d['C_out']]))

        k_exch = 1.0 / building_d['R_exch']
        k_floor = 1.0 / building_d['R_floor']
        k_vent = 1.0 / building_d['R_vent']
        k_cond = 1.0 / building_d['R_cond']

        conductance_matrix = np.array([[k_vent + k_exch + k_floor, -k_exch], [-k_exch, k_cond + k_exch]])
        conductance_matrix_amb = np.array([[k_vent, k_floor], [k_cond, 0]])

        mat_index = pyo.RangeSet(1, len(capacitance_matrix))
        self.model.C_house = pyo.Param(mat_index, mat_index, initialize=self.mat2dict(capacitance_matrix))
        self.model.K_house = pyo.Param(mat_index, mat_index, initialize=self.mat2dict(conductance_matrix))
        self.model.K_house_amb = pyo.Param(mat_index, mat_index, initialize=self.mat2dict(conductance_matrix_amb))
        self.model.window_area = pyo.Param(initialize=building_d['A_glass'])

        # Heat pump
        self.model.Q_nom = pyo.Param(within=pyo.NonNegativeReals, initialize=hybrid_heat_pump.heatPumpThermalPower)
        self.model.min_rel_heat = pyo.Param(within=pyo.NonNegativeReals, initialize=0.3)
        self.model.C_buffer = pyo.Param(within=pyo.NonNegativeReals, initialize=hybrid_heat_pump_d['buffer_capacitance'])
        self.model.T_buffer_min = pyo.Param(within=pyo.NonNegativeReals, initialize=hybrid_heat_pump_d['buffer_temp_min'])
        self.model.T_buffer_max = pyo.Param(within=pyo.NonNegativeReals, initialize=hybrid_heat_pump_d['buffer_temp_max'])
        self.model.T_buffer_hor = pyo.Param(within=pyo.NonNegativeReals, initialize=hybrid_heat_pump_d['buffer_temp_hor'])
        self.model.T_house_min = pyo.Param(within=pyo.NonNegativeReals, initialize=hybrid_heat_pump_d['house_temp_min'])
        self.model.T_house_max = pyo.Param(within=pyo.NonNegativeReals, initialize=hybrid_heat_pump_d['house_temp_max'])
        self.model.T_house_hor = pyo.Param(within=pyo.NonNegativeReals, initialize=hybrid_heat_pump_d['house_temp_hor'])

        cops = [self.calculate_cop(hybrid_heat_pump_d['buffer_temp_set'], T_air) for T_air in air_temperature]
        self.model.cop = pyo.Param(self.model.time_index_p, within=pyo.NonNegativeReals, initialize=self.it2dict(cops))

        # initial values from input
        self.model.T_in_0 = pyo.Param(initialize=house_temperatures[0])
        self.model.T_out_0 = pyo.Param(initialize=house_temperatures[1])
        self.model.T_buffer_0 = pyo.Param(initialize=buffer_temperature)

        # Variables
        # Powers
        self.model.Q_to_buffer = pyo.Var(self.model.time_index_p, within=pyo.NonNegativeReals, initialize=0)
        self.model.Q_to_house = pyo.Var(self.model.time_index_p, within=pyo.NonNegativeReals, initialize=0)
        self.model.p_hhp = pyo.Var(self.model.time_index_p, within=pyo.NonNegativeReals, initialize=0)
        self.model.z_on = pyo.Var(self.model.time_index_p, within=pyo.Binary, initialize=0)

        # Temperatures
        self.model.T_buffer = pyo.Var(self.model.time_index_soc, within=pyo.NonNegativeReals, initialize=self.model.T_buffer_0)
        self.model.T_in = pyo.Var(self.model.time_index_soc, within=pyo.NonNegativeReals, initialize=self.model.T_in_0)
        self.model.T_out = pyo.Var(self.model.time_index_soc, within=pyo.NonNegativeReals, initialize=self.model.T_out_0)
        # Temperature slack variables to ensure feasibility of the problem
        self.model.slack_soc_max = pyo.Param(self.model.time_index_soc, within=pyo.NonNegativeReals, initialize=0)
        self.model.slack_soc_min = pyo.Param(self.model.time_index_soc, within=pyo.NonNegativeReals, initialize=0)

        # Operational
        # Bounds
        self.model.con_hp_ch_min = pyo.Constraint(
            self.model.time_index_p, rule=lambda m, t:
            m.Q_to_buffer[t] >= m.z_on[t] * m.min_rel_heat * m.Q_nom
        )

        self.model.con_hp_ch_max = pyo.Constraint(
            self.model.time_index_p, rule=lambda m, t:
            m.Q_to_buffer[t] <= m.z_on[t] * m.Q_nom
        )

        self.model.con_buffer_temp_min = pyo.Constraint(
            self.model.time_index_soc, rule=lambda m, t:
            m.T_buffer[t] >= m.T_buffer_min
        )

        self.model.con_house_temp_min = pyo.Constraint(
            self.model.time_index_soc, rule=lambda m, t:
            m.T_in[t] >= m.T_house_min - m.slack_soc_min[t]
        )

        self.model.con_buffer_temp_max = pyo.Constraint(
            self.model.time_index_soc, rule=lambda m, t:
            m.T_buffer[t] <= m.T_buffer_max
        )

        # Enforce max temperature in house if it is not heated above the max naturally (due to the weather)
        if not self.exceed_upper_temp_house_2(hybrid_heat_pump, house_temperatures, air_temperature, soil_temperature,
                                            solar_irradiance, capacitance_matrix, conductance_matrix,
                                            conductance_matrix_amb):

            self.model.con_house_temp_max = pyo.Constraint(
                self.model.time_index_soc, rule=lambda m, t:
                m.T_in[t] <= m.T_house_max + m.slack_soc_max[t]
            )
        else:
            # set slack_soc_max as an param to 0 to increase stability of the solver
            self.model.slack_soc_max = pyo.Param(self.model.time_index_soc, within=pyo.NonNegativeReals, initialize=0)

        # Initial Conditions
        self.model.con_buffer_temp_init = pyo.Constraint(rule=lambda m: m.T_buffer[m.time_index_soc.first()] == m.T_buffer_0)
        self.model.cnstr_T_in0 = pyo.Constraint(rule=lambda m: m.T_in[self.model.time_index_soc.first()] == m.T_in_0)
        self.model.cnstr_T_out0 = pyo.Constraint(rule=lambda m: m.T_out[self.model.time_index_soc.first()] == m.T_out_0)

        # Final Conditions
        self.model.con_buffer_temp_hor = pyo.Constraint(rule=lambda m: m.T_buffer[m.time_index_soc.last()] >= m.T_buffer_hor)
        self.model.con_house_temp_hor = pyo.Constraint(rule=lambda m: m.T_in[m.time_index_soc.last()] >= m.T_house_hor)

        # update temperatures
        self.model.con_buffer_temp_update = pyo.Constraint(
            self.model.time_index_soc, rule=lambda m, t:
            m.C_buffer * m.T_buffer[t + 1] == m.C_buffer * m.T_buffer[t] + (
                    m.Q_to_buffer[t] - m.Q_to_house[t]) * m.dt
            if t < m.time_index_soc.last() else pyo.Constraint.Skip
        )

        def constraint_update_T_in(m, t):
            KT = m.K_house[1, 1] * m.T_in[t] + m.K_house[1, 2] * m.T_out[t]
            KT_amb = m.K_house_amb[1, 1] * m.T_air[t] + m.K_house_amb[1, 2] * m.T_soil[t]
            solar = m.window_area * m.I_sol[t]
            hp = m.Q_to_house[t]

            return (m.C_house[1, 1] * m.T_in[t + 1] == m.C_house[1, 1] * m.T_in[t] + m.dt *
                    (-KT + KT_amb + solar + hp))

        def constraint_update_T_out(m, t):
            KT = m.K_house[2, 1] * m.T_in[t] + m.K_house[2, 2] * m.T_out[t]
            KT_amb = m.K_house_amb[2, 1] * m.T_air[t] + m.K_house_amb[2, 2] * m.T_soil[t]
            solar = 0.0
            hp = 0.0
            constraint = (m.C_house[2, 2] * m.T_out[t + 1] == m.C_house[2, 2] * m.T_out[t] + m.dt *
                         (-KT + KT_amb + solar + hp))
            return constraint

        self.model.con_update_T_in = pyo.Constraint(self.model.time_index_p, rule=constraint_update_T_in)
        self.model.con_update_T_out = pyo.Constraint(self.model.time_index_p, rule=constraint_update_T_out)

        # definition pyo.Constraint
        self.model.con_P = pyo.Constraint(
            self.model.time_index_p, rule=lambda m, t:
            m.Q_to_buffer[t] == m.p_hhp[t] * m.cop[t]
        )
        self.has_heat_pump = True

    def create_energy_balance(self, asset_portfolio: dict):
        self.model.e_buy = pyo.Var(self.model.time_index_p, within=pyo.NonNegativeReals, initialize=0)
        self.model.e_sell = pyo.Var(self.model.time_index_p, within=pyo.NonNegativeReals, initialize=0)
        self.model.z_buy = pyo.Var(self.model.time_index_p, within=pyo.Binary, initialize=0)

        capacity = 17.0e3  # TODO: remove magic number
        self.model.con_energy_buy_ub = pyo.Constraint(
            self.model.time_index_p, rule=lambda m, t:
            m.e_buy[t] <= m.z_buy[t] * capacity * m.dt
        )

        self.model.con_energy_sell_ub = pyo.Constraint(
            self.model.time_index_p, rule=lambda m, t:
            m.e_sell[t] <= (1 - m.z_buy[t]) * capacity * m.dt
        )

        def con_energy_buy_f(m, t):
            e_buy = 0.0
            if 'ElectricityDemand' in asset_portfolio:
                e_buy += m.p_edemand[t] * m.dt
            if 'PVInstallation' in asset_portfolio:
                e_buy -= m.p_pv_use[t] * m.dt
            if 'Battery' in asset_portfolio:
                e_buy += (m.p_ch[t] - m.p_bat_use[t]) * m.dt
            if 'HeatPump' in asset_portfolio:
                e_buy += m.p_hp[t] * m.dt
            if 'HybridHeatPump' in asset_portfolio:
                e_buy += m.p_hhp[t] * m.dt
            if 'EVChargingStation' in asset_portfolio:
                e_buy += m.p_ev[t] * m.dt

            return m.e_buy[t] == e_buy

        self.model.con_energy_buy = pyo.Constraint(self.model.time_index_p, rule=con_energy_buy_f)

        def con_energy_sell_f(m, t):
            e_sell = 0.0
            if 'PVInstallation' in asset_portfolio:
                e_sell += m.p_pv_sell[t] * m.dt
            if 'Battery' in asset_portfolio:
                e_sell += m.p_bat_sell[t] * m.dt
            return m.e_sell[t] == e_sell

        self.model.con_energy_sell = pyo.Constraint(self.model.time_index_p, rule=con_energy_sell_f)

    def get_first_value_from_component(self, name: str):
        # component is either an IndexedVar or IndexedParam
        component = self.model.find_component(name)
        if isinstance(component, IndexedVar):
            return next(iter(component.values()))()
        elif isinstance(component, IndexedParam):
            return next(iter(component.values()))
        else:
            raise TypeError(f'Component {name} should be IndexedVar or IndexedParam')

    def get_value_from_component(self, name: str):
        # component is either an ScalarVar or ScalarParam
        component = self.model.find_component(name)
        if isinstance(component, ScalarVar) or isinstance(component, ScalarParam):
            return pyo.value(component)
        else:
            raise TypeError(f'Component {name} should be IndexedVar or IndexedParam')

    def create_objective_function(self, is_grid_tariff: bool):
        def total_costs(m):
            # minimize slack variables to minimize constraint violation
            if self.has_heat_pump:
                slack_costs = sum(1.0e3 * m.slack_soc_min[t] + 1.0e3 * m.slack_soc_max[t] for t in m.time_index_p)
            else:
                slack_costs = 0.0
            costs = m.buy_costs - m.sell_rev + slack_costs
            if is_grid_tariff:
                costs += m.grid_costs
            return costs

        self.model.objective_function = pyo.Objective(sense=pyo.minimize, expr=total_costs)

        # Set model variables and parameters after constructing the problem
        # This allows for grabbing the
        self.model_variables = self.model.component_map(ctype=pyo.Var)
        self.model_parameters = self.model.component_map(ctype=pyo.Param)

    def create_sell_revenues(self,
                             energy_contract: str,
                             dynamic_flat_price: float,
                             static_price: float,
                             da_prices: list,
                             is_feed_in_tariff: bool,
                             feed_in_price: float):

        """
        Create costs for buying energy
        Prices depend on the nature of the energy contract (static/dynamic)
        And whether there is a feed-in tariff
        - dynamic: price = flat_price + da_price or da_price if feed-in
        - static: price = static_price or feed_in_price if feed-in
        """
        self.model.sell_rev = pyo.Var(within=pyo.Reals, initialize=0)
        if energy_contract == 'dynamic':
            if is_feed_in_tariff:
                sell_prices = da_prices
            else:
                sell_prices = [price + dynamic_flat_price for price in da_prices]
        else:
            if is_feed_in_tariff:
                sell_prices = len(self.model.time_index_p) * [feed_in_price]
            else:
                sell_prices = len(self.model.time_index_p) * [static_price]

        # Convert e_buy from J to kWh to match the price unit Eur/kWh
        self.model.sell_rev_def = pyo.Constraint(
            rule=lambda m: m.sell_rev == sum(sell_prices[t] * m.e_sell[t] / 3.6e6 for t in m.time_index_p))

    def create_buy_costs(self,
                         energy_contract: str,
                         dynamic_flat_price: float,
                         static_price: float,
                         da_prices: list):
        """
        Create costs for buying energy
        Prices depend on the nature of the energy contract (static/dynamic)
        - dynamic: price = flat_price + da_price
        - static: price = static_price
        """
        self.model.buy_costs = pyo.Var(within=pyo.Reals, initialize=0)
        # Determine costs from buying energy
        if energy_contract == 'dynamic':
            buy_prices = [price + dynamic_flat_price for price in da_prices]
        else:
            buy_prices = len(self.model.time_index_p) * [static_price]

        # Convert e_buy from J to kWh to match the price unit Eur/kWh
        self.model.buy_costs_def = pyo.Constraint(
            rule=lambda m: m.buy_costs == sum(buy_prices[t] * m.e_buy[t] / 3.6e6 for t in m.time_index_p))

    def solve(self, mip_gap, show_logs=False):
        # Use open-source highs solver, installed in the highspy package (see requirements)
        # There are some issues with how pyomo handles the logging from the highs solver
        # This issue is related to: https://github.com/Pyomo/pyomo/issues/3031
        # For this reason, the show_logs is set to False in this example
        opt = SolverFactory('glpk')
        opt.options['mipgap'] = mip_gap
        # opt.log_stream = None
        # opt.keepfiles = True
        # opt.log_stream = open("highs_output.log", "w")
        status = opt.solve(self.model, tee=show_logs)

        LOGGER.info(f"Status = {status.solver.termination_condition}")
        assert status.solver.termination_condition != 'infeasible', "solution status infeasible"
        assert status.solver.termination_condition != 'infeasibleOrUnbounded', "solution status infeasible or unbounded"

    def create_static_bw_tariff(self,
                                static_bw_price_low: float,
                                static_bw_price_high: float,
                                static_bw_power: float):

        self.model.static_bw_price_low = pyo.Param(within=pyo.NonNegativeReals, initialize=static_bw_price_low)
        self.model.static_bw_price_high = pyo.Param(within=pyo.NonNegativeReals, initialize=static_bw_price_high)
        self.model.static_bw_power = pyo.Param(within=pyo.NonNegativeReals, initialize=static_bw_power)
        self.model.static_bw_costs = pyo.Var(self.model.time_index_p, within=pyo.NonNegativeReals, initialize=0)
        self.model.grid_costs = pyo.Var(within=pyo.NonNegativeReals, initialize=0)

        # Constraints
        self.model.con_bw_low = pyo.Constraint(
            self.model.time_index_p, rule=lambda m, t:
            # eur/kWh x kWh
            m.static_bw_price_high * (- (m.e_buy[t] + m.e_sell[t]) - m.static_bw_power * m.dt)/3.6e6 <= m.static_bw_costs[t])

        self.model.con_bw_high = pyo.Constraint(
            self.model.time_index_p, rule=lambda m, t:
            # eur/kWh x kWh
            m.static_bw_price_high * ((m.e_buy[t] + m.e_sell[t]) - m.static_bw_power * m.dt)/3.6e6 <= m.static_bw_costs[t])

        self.model.con_grid_costs = pyo.Constraint(rule=lambda m: m.grid_costs == sum(m.static_bw_costs[t] for t in m.time_index_p))

    def add_static_bw_tariff(self, incentive_inputs: dict):
        # Params and variables
        self.model.static_bw_price_low = pyo.Param(within=pyo.NonNegativeReals, initialize=incentive_inputs['static_bw_price_low'])
        self.model.static_bw_price_high = pyo.Param(within=pyo.NonNegativeReals, initialize=incentive_inputs['static_bw_price_high'])
        self.model.static_bw_power = pyo.Param(within=pyo.NonNegativeReals, initialize=incentive_inputs['static_bw_power'])

        self.model.static_bw_costs = pyo.Var(self.model.time_index_p, within=pyo.NonNegativeReals, initialize=0)

        # Constraints
        self.model.con_bw_low = pyo.Constraint(
            self.model.time_index_p, rule=lambda m, t:
            # eur/kWh x kWh
            m.static_bw_price_high * (- (m.e_buy[t] + m.e_sell[t]) - m.static_bw_power * m.dt)/3.6e6 <= m.static_bw_costs[t])

        self.model.con_bw_high = pyo.Constraint(
            self.model.time_index_p, rule=lambda m, t:
            # eur/kWh x kWh
            m.static_bw_price_high * ((m.e_buy[t] + m.e_sell[t]) - m.static_bw_power * m.dt)/3.6e6 <= m.static_bw_costs[t])

    def create_variable_tariff(self, variable_tariff: list):
        variable_tariff_dict = self.it2dict(variable_tariff)
        self.model.variable_tariff = pyo.Param(self.model.time_index_p, within=pyo.NonNegativeReals,
                                               initialize=variable_tariff_dict)

        self.model.grid_costs = pyo.Var(within=pyo.NonNegativeReals, initialize=0)

        self.model.con_grid_costs = pyo.Constraint(
            rule=lambda m: m.grid_costs == sum(m.variable_tariff[t] * (m.e_buy[t] + m.e_sell[t])/3.6e6
                                               for t in m.time_index_p))

    def create_variable_peak_tariff(self,
                                    variable_peak_tariff: list,
                                    peak_costs: float):
        if peak_costs < 0.0:
            peak_costs = 0.0

        LOGGER.debug(f"Amount of peak tarrifs: {len(variable_peak_tariff)}")
        # Params and variables
        variable_peak_tariff_dict = self.it2dict(variable_peak_tariff)
        LOGGER.debug(f"Amount of peak tarrifs_dict: {len(variable_peak_tariff_dict)}")
        LOGGER.debug(f"peak tarrifs_dict: {variable_peak_tariff_dict}")
        self.model.variable_peak_tariff = pyo.Param(self.model.time_index_p, within=pyo.NonNegativeReals,
                                                    initialize=variable_peak_tariff_dict)

        self.model.peak_costs_old = pyo.Param(within=pyo.NonNegativeReals, initialize=peak_costs)

        self.model.peak_costs = pyo.Var(self.model.time_index_p, within=pyo.NonNegativeReals, initialize=0)
        self.model.peak_costs_max = pyo.Var(within=pyo.NonNegativeReals, initialize=0.0)

        self.model.grid_costs = pyo.Var(within=pyo.NonNegativeReals, initialize=0)

        # Constraints
        self.model.con_peak_costs = pyo.Constraint(
            self.model.time_index_p, rule=lambda m, t:
            m.peak_costs[t] == (m.e_buy[t] + m.e_sell[t]) / (m.dt * 1000.0) * m.variable_peak_tariff[t]  # kW x eur/kW
        )

        self.model.con_peak_costs_max = pyo.Constraint(
            self.model.time_index_p, rule=lambda m, t:
            m.peak_costs_max >= m.peak_costs[t]
        )

        self.model.con_peak_costs_old = pyo.Constraint(
            rule=lambda m: m.peak_costs_max >= m.peak_costs_old
        )

        self.model.con_grid_costs = pyo.Constraint(rule=lambda m: m.grid_costs == m.peak_costs_max)

    def exceed_upper_temp_house_2(self,
                                heat_pump: esdl.EnergyAsset,
                                house_temperatures: list,
                                air_temperature: list,
                                soil_temperature: list,
                                solar_irradiance: list,
                                capacitance_matrix: np.array,
                                conductance_matrix: np.array,
                                conductance_matrix_amb: np.array):

        """
        Calculate whether the upper temperature limit is surpassed without using the (H)HP
        We calculate the house temperature induced by the weather by solving the heat transfer equations of the house
        , using Euler's method
        """

        T = np.array(house_temperatures)
        heat_pump_d = json.loads(heat_pump.description)
        dt = pyo.value(self.model.dt)

        if T[0] > heat_pump_d['house_temp_max']:
            return True
        for t in range(len(self.model.time_index_p)):
            # calculate right hand side (rhs) of the differential equation.
            T_amb = np.array([air_temperature[t], soil_temperature[t]])
            rhs = (-np.matmul(conductance_matrix, T) +
                   np.matmul(conductance_matrix_amb, T_amb) +
                   np.array([pyo.value(self.model.window_area) * solar_irradiance[t]]))
            T += dt * np.matmul(np.diag(1.0/np.diag(capacitance_matrix)), rhs)
            if T[0] < heat_pump_d['house_temp_min']:
                T[0] = heat_pump_d['house_temp_min']
            if T[0] > heat_pump_d['house_temp_max']:
                return True
        return False

    @staticmethod
    def it2dict(iterator) -> dict:
        return {i: v for i, v in enumerate(iterator)}

    @staticmethod
    def mat2dict(matrix: np.array) -> dict:
        d = dict()
        for i in range(matrix.shape[0]):
            for j in range(matrix.shape[1]):
                d[(i + 1, j + 1)] = matrix[i, j]
        return d

    @staticmethod
    def calculate_cop(T_set, T_out):
        dT = T_set - T_out
        return 8.736555867367798 - 0.18997851 * dT + 0.00125921 * dT ** 2

