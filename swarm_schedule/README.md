# Swarm Schedule

A swarm intelligence-based scheduling engine.

## Overview

Swarm Schedule uses swarm intelligence algorithms (Particle Swarm Optimization, Ant Colony Optimization) to solve complex scheduling problems efficiently.

## Features

- **Particle Swarm Optimization (PSO)** - Global optimization for schedule parameters
- **Ant Colony Optimization (ACO)** - Discrete assignment problems
- **Hybrid approaches** - Combine swarm methods with constraint propagation

## Installation

```bash
cd swarm_schedule
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
python -m swarm_schedule --help
```

## Project Structure

```
swarm_schedule/
├── src/
│   └── swarm_schedule/
│       ├── __init__.py
│       ├── core.py          # Core scheduling models
│       ├── pso.py           # Particle Swarm Optimization
│       ├── aco.py           # Ant Colony Optimization
│       └── cli.py           # Command-line interface
├── tests/
│   └── test_core.py
├── requirements.txt
└── pyproject.toml
```
