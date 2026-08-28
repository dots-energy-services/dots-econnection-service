import numpy as np
from numpy.linalg import inv
from typing import Optional
from dots_infrastructure.Logger import LOGGER


class House:
    # solar is left out for now, because we obtain these from the heat profile generator
    def __init__(self, capacities: dict, resistances: dict, window_area: float):
        # Create capacity matrix and its inverse
        self.C = np.diag(np.array([capacities['C_in'], capacities['C_out']]))
        self.C_inv = inv(self.C)

        # Create heat conductance matrices and their inverse
        k_exch = 1.0 / resistances['R_exch']
        k_floor = 1.0 / resistances['R_floor']
        k_vent = 1.0 / resistances['R_vent']
        k_cond = 1.0 / resistances['R_cond']

        # Estimate total conductance with parallel circuit of floor, transm, and ventilation
        k_transm = 1.0/(1.0/k_exch + 1.0/k_cond)  # in series
        self.k_total = k_floor + k_transm + k_vent

        self.K = np.array([[k_vent + k_exch + k_floor, -k_exch], [-k_exch, k_cond + k_exch]])
        self.K_amb = np.array([[k_vent, k_floor], [k_cond, 0]])

        # Note that both K and K_amb are diagonally dominant and thus invertible
        self.K_inv = inv(self.K)
        self.K_amb_inv = inv(self.K_amb)

        # precomputed matrices
        self.A = np.matmul(self.C_inv, self.K)
        self.A_amb = np.matmul(self.C_inv, self.K_amb)
        self.A_inv = inv(self.A)

        self.exponential_matrix = None

        self.window_area = window_area
        self.shgc = 0.7  # solar heat gain coefficient

        self.temperatures: Optional[np.array] = None  # fill later if weather conditions are known

    def __str__(self):
        return f'House instance with: \n capacitances:\n {self.C} \n conductances:\n {self.K}\n  and\n {self.K_amb}'

    def set_initial_temperatures(self, initial_temp_in: float, nominal_heat: float,
                                 air_temperature: float, soil_temperature: float, solar_irradiance: float):
        # Idea calculate the initial_temp_out by assuming thermal equilibrium between the outside and inside,
        # we solve for T[1] and heat_to_house
        # We thus solve
        # 0 = -K T + K_amb T_amb + solar_vector + heat_to_house_vector, for T[1]
        # We use: K T = T[0]K[:, 0]  + T[1]K[:, 1]
        # so: [[-1, K21], [0, K22]] [heat_to_house, T[1]] = K_amb T_amb + solar_vector - T[0]K[:, 0]
        ambient_temperatures = np.array([air_temperature, soil_temperature])
        solar_vector = np.array([self.window_area * solar_irradiance, 0.0])

        # write like Ax = b
        A = self.K.copy()
        A[:, 0] = np.array([-1.0, 0.0])
        b = np.matmul(self.K_amb, ambient_temperatures) + solar_vector - initial_temp_in * self.K[:, 0].T
        x = np.linalg.solve(A, b)
        required_heat_to_house = x[0]
        LOGGER.info(f"Required heat to house: {required_heat_to_house}")
        LOGGER.info(f"Nominal heat: {nominal_heat}")
        heat_to_house = np.clip(required_heat_to_house, 0, nominal_heat)
        temperatures = np.linalg.solve(self.K, np.matmul(self.K_amb, ambient_temperatures) +
                                       solar_vector + np.array([heat_to_house, 0]))
        print(f"Temperatures: {temperatures}")
        LOGGER.info(f"Target house temperature: {initial_temp_in}")
        LOGGER.info(f"Initial house temperatures: {temperatures}")
        # If heating was required, it should have been be satisfied by the heat pump and we should be at the set point.
        # If not, the temperature in the house will be higher then the set point
        if required_heat_to_house >= 0:
            assert abs(initial_temp_in - temperatures[0]) < 1.0e-3, 'internal temperature should be as provided'
        self.temperatures = temperatures

    def get_temperatures(self):
        return self.temperatures

    def update_temperatures(self, time_step: float, air_temperature: float, soil_temperature: float,
                            solar_irradiance: float, heat_to_house: float):
        # Define help vectors
        ambient_temperatures = np.array([air_temperature, soil_temperature])
        solar_vector = np.array([self.window_area * solar_irradiance, 0.0])
        heat_to_house_vector = np.array([heat_to_house, 0.0])

        # Differential equation is:
        # C dT/dt = -K T + K_amb T_amb + solar_vector + heat_to_house_vector
        val = time_step * np.matmul(self.C_inv, - np.matmul(self.K, self.temperatures) +
                      np.matmul(self.K_amb, ambient_temperatures) +
                      solar_vector + heat_to_house_vector)
        self.temperatures += val


class HeatBuffer:
    def __init__(self, buffer_capacitance):
        self.capacitance = buffer_capacitance
        self.temperature: Optional[float] = None

    def set_initial_temperature(self, initial_buffer_temp: float):
        self.temperature = initial_buffer_temp

    def get_buffer_temperature(self):
        return self.temperature

    def update_temperature(self, time_step: float, heat_out: float, heat_in: float):
        energy_to_buffer = (heat_in - heat_out) * time_step
        self.temperature += energy_to_buffer/self.capacitance


class objectfunctions:
    def get_building_of_hp(self, esdl_id):
        assert isinstance(self.esdl_objects[esdl_id].eContainer(), esdl.Building), f"Container of asset {esdl_id} " \
                                                                                   f"is not a building"
        return self.esdl_objects[esdl_id].eContainer()