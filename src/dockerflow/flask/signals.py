from flask.signals import Namespace

dockerflow_signals = Namespace()

heartbeat_passed = dockerflow_signals.signal('heartbeat-passed')
heartbeat_failed = dockerflow_signals.signal('heartbeat-failed')
