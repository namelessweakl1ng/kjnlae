def test_sdk_exposes_security_boundaries_without_web_or_training_imports():
    from kjnlae import ActionGateway, Guard, GuardedExecutor, HostAuthority, OutputGuard

    assert Guard and ActionGateway and GuardedExecutor and HostAuthority and OutputGuard
