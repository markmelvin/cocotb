''' Copyright (c) 2013 Potential Ventures Ltd
Copyright (c) 2013 SolarFlare Communications Inc
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:
    * Redistributions of source code must retain the above copyright
      notice, this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above copyright
      notice, this list of conditions and the following disclaimer in the
      documentation and/or other materials provided with the distribution.
    * Neither the name of Potential Ventures Ltd,
      SolarFlare Communications Inc nor the
      names of its contributors may be used to endorse or promote products
      derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL POTENTIAL VENTURES LTD BE LIABLE FOR ANY
DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE. '''

"""
Cocotb is a coroutine, cosimulation framework for writing testbenches in Python.

See http://cocotb.readthedocs.org for full documentation
"""
import os
import sys
import logging
import threading
import random
import time


import cocotb.handle
from cocotb.scheduler import Scheduler
from cocotb.log import SimLogFormatter, SimBaseLog, SimLog
from cocotb.regression import RegressionManager


# Things we want in the cocotb namespace
from cocotb.decorators import test, coroutine, function, external

# Singleton scheduler instance
# NB this cheekily ensures a singleton since we're replacing the reference
# so that cocotb.scheduler gives you the singleton instance and not the
# scheduler package

# GPI logging instance
# For autodocumentation don't need the extension modules
if "SPHINX_BUILD" not in os.environ:
    logging.basicConfig()
    logging.setLoggerClass(SimBaseLog)
    log = SimLog('cocotb.gpi')

scheduler = Scheduler()
regression = None

plusargs = {}

# To save typing provide an alias to scheduler.add
fork = scheduler.add

class TestFailed(Exception):
    pass



# FIXME is this really required?
_rlock = threading.RLock()

def mem_debug(port):
    import cocotb.memdebug
    memdebug.start(port)

def _initialise_testbench(root_handle):
    """
    This function is called after the simulator has elaborated all
    entities and is ready to run the test.

    The test must be defined by the environment variables
        MODULE
        TESTCASE
    """
    _rlock.acquire()

    memcheck_port = os.getenv('MEMCHECK')
    if memcheck_port is not None:
        mem_debug(int(memcheck_port))

    # Seed the Python random number generator to make this repeatable
    seed = os.getenv('RANDOM_SEED')
    if seed is None:
        seed = int(time.time())
        log.info("Seeding Python random module with %d" % (seed))
    else:
        seed = int(seed)
        log.info("Seeding Python random module with supplied seed %d" % (seed))
    random.seed(seed)

    exec_path = os.getenv('SIM_ROOT')
    if exec_path is None:
        exec_path = 'Unknown'

    version = os.getenv('VERSION')
    if version is None:
        log.info("Unable to determine Cocotb version from %s" % exec_path)
    else:
        log.info("Running tests with Cocotb v%s from %s" % (version, exec_path))

    # Create the base handle type
    dut = cocotb.handle.SimHandle(root_handle)

    process_plusargs()

    module_str = os.getenv('MODULE')
    test_str = os.getenv('TESTCASE')

    if not module_str:
        raise ImportError("Environment variables defining the module(s) to \
                        execute not defined.  MODULE=\"%s\"\"" % (module_str))

    modules = module_str.split(',')

    global regression

    regression = RegressionManager(dut, modules, tests=test_str)
    regression.initialise()
    regression.execute()

    _rlock.release()
    return True

def _sim_event(level, message):
    """Function that can be called externally to signal an event"""
    SIM_INFO = 0
    SIM_TEST_FAIL = 1
    SIM_FAIL = 2
    from cocotb.result import TestFailure

    if level is SIM_TEST_FAIL:
        scheduler.log.error("Failing test at simulator request")
        scheduler.finish_test(TestFailure("Failure from external source: %s" % message))
    elif level is SIM_FAIL:
        scheduler.log.error("Failing test at simulator request before test run completion: %s" % message)
        scheduler.finish_scheduler(TestFailure("Failing test at simulator request before test run completion"))
    else:
        scheduler.log.error("Unsupported sim event")


def process_plusargs():

    global plusargs

    plusargs = {}

    for option in cocotb.argv:
        if option.startswith('+'):
            if option.find('=') != -1:
                (name, value) = option[1:].split('=')
                plusargs[name] = value
            else:
                plusargs[option[1:]] = True

