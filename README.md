
# Calculation service for esdl_type EConnection:

This calculation service calculates the cost-optimal dispatch of a portfolio of assets within a house. It uses a moving-horizon optimization of some limited horizon (e.g. 12 hours). It assumes perfect knowledge of parameters within the optimization horizon. The costs for the house are the sum of the energy costs, which depend on whether the household has a static of dynamic energy contract, and the grid tariff. The flexible assets implemented are photovoltaics, electric vehicles, home batteries, heat pumps and hybrid heat pumps. For more details on the modeling of the energy management system, the paper: On synergies between congestion management instruments: The Dutch case-study, which should be publicly available

## Calculations

### calculate_dispatch 

Calculate the dispatch of of all assets in the portfolio. It does so by 1) Create a portfolio optimization problem (single phase), 2) Solves the optimization model for the dispatch of the assets, 3)read the return values from the model, and 4) compute the (3 phase unbalanced) dispatch for the assets and the aggregate
#### Input parameters
|Name            |esdl_type            |data_type            |unit            |description            |
|----------------|---------------------|---------------------|----------------|-----------------------|
|solar_irradiance|EnvironmentalProfiles|VECTOR|Wm2|The expected solar irradiance for the coming 12 hours as predicted by the weather service.|
|air_temperature|EnvironmentalProfiles|VECTOR|K|The expected air temperature for the coming 12 hours as predicted by the weather service.|
|soil_temperature|EnvironmentalProfiles|VECTOR|K|The expected soil temperature for the coming 12 hours as predicted by the weather service.|
|active_power|ElectricityDemand|VECTOR|W|The expected active power demand from the base load for the coming 12 hours as predicted by the electriciy demand service.|
|reactive_power|ElectricityDemand|VECTOR|VAr|The expected reactive power demand from the base load for the coming 12 hours as predicted by the electriciy demand service.|
|potential_active_power|PVInstallation|VECTOR|W|The expected active power generation for the coming 12 hours as predicted by the pv service.|
|dhw_temperature|HeatPump|DOUBLE|K|Current temperature in the domestic hot water tank of the heat pump system.|
|buffer_temperature|HeatPump|DOUBLE|K|Current temperature in the space heating tank of the heat pump system.|
|house_temperatures|HeatPump|VECTOR|K|Current temperatures in interior and envelope of the house, as communicated by the heat pump.|
|buffer_temperature|HybridHeatPump|DOUBLE|K|Current temperature in the space heating tank of the hybrid heat pump system.|
|house_temperatures|HybridHeatPump|VECTOR|K|Current temperatures in interior and envelope of the house, as communicated by the hybrid heat pump.|
|state_of_charge_ev|EVChargingStation|DOUBLE|J|Current state of charge in the electric vehicle|
#### Output values
|Name             |data_type             |unit             |description             |
|-----------------|----------------------|-----------------|------------------------|
|aggregated_active_power|VECTOR|W|The total active power dispatch of the house accross the 3 phases|
|aggregated_reactive_power|VECTOR|VAr|The total reactive power dispatch of the house accross the 3 phases|
|dispatch_pv|DOUBLE|W|Dispatch of the pv installation|
|dispatch_ev|DOUBLE|W|Dispatch of the electric vehicles|
|heat_power_to_tank_dhw|DOUBLE|W|Amount of heat the heat pump brings into the domestic hot water tank.|
|heat_power_to_buffer|DOUBLE|W|Amount of heat the heat pump brings into the space heating tank.|
|heat_power_to_dhw|DOUBLE|W|Amount of heat that gets removed from the domestic hot water tank for heating water.|
|heat_power_to_house|DOUBLE|W|Amount of heat that gets removed from the space heating water tank for space heating.|
|heat_power_to_buffer_hhp|DOUBLE|W|Amount of heat the hybrid heat pump brings into the space heating tank.|
|heat_power_to_house_hhp|DOUBLE|W|Amount of heat that gets removed from the space heating water tank for space heating.|

### Relevant links
|Link             |description             |
|-----------------|------------------------|
|[emservice](https://energytransition.github.io/#router/doc-content/687474703a2f2f7777772e746e6f2e6e6c2f6573646c/EConnection.html)|Details on the EConnection esdl type|
|[modeling](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4992392&adobe_mc=MCMID%3D91243400954555169556066193574155036964%7CMCORGID%3D4D6368F454EC41940A4C98A6%2540AdobeOrg%7CTS%3D1745930123)|Details on the modeling of the energy management system|
