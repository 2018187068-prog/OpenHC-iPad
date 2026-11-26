int openhc_platform_probe(void) { return 90; }
int openhc_btstack_probe(void) { return 90; }
int openhc_btstack_services_probe(void) { return 90; }
int openhc_btstack_control_synthetic(const char *address, unsigned channel,
                                     const char *profile, const char *run_dir) {
    (void)address; (void)channel; (void)profile; (void)run_dir;
    return 90;
}
int openhc_btstack_control_inbound(const char *run_dir) { (void)run_dir; return 90; }
int openhc_btstack_ownership_probe(void) { return 90; }
int openhc_session_owner_probe(void) { return 90; }
