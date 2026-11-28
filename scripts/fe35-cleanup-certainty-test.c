#include <stdio.h>
#include "../theos/Fe35CleanupCertainty.h"

static int check(const char *name, int expected, int actual) {
    if (expected == actual) return 0;
    fprintf(stderr, "CLEANUP_CERTAINTY_FAIL=%s,%d,%d\n", name, expected, actual);
    return 1;
}

int main(void) {
    int failures = 0;
#define CASE(name, expected, ...) \
    failures += check(name, expected, openhc_fe35_cleanup_confirmed(__VA_ARGS__))
    /* Known auth-CID peer close: protocol may fail while all cleanup is confirmed. */
    CASE("auth-peer-close-clean", 1, 1, 1, 0, 0, 1, 1, 1, 1, 1);
    CASE("cleanup-barrier-failed", 0, 0, 1, 0, 0, 1, 1, 1, 1, 1);
    CASE("transport-close-failed", 0, 1, 0, 0, 0, 1, 1, 1, 1, 1);
    CASE("registration-pending", 0, 1, 1, 1, 0, 1, 1, 1, 1, 1);
    CASE("cleanup-unconfirmed", 0, 1, 1, 0, 1, 1, 1, 1, 1, 1);
    CASE("cid-never-settled", 0, 1, 1, 0, 0, 1, 0, 0, 1, 1);
    CASE("auth-cid-never-settled", 0, 1, 1, 0, 0, 1, 1, 1, 1, 0);
    CASE("unowned-cids", 1, 1, 1, 0, 0, 0, 0, 0, 0, 0);
#undef CASE
    if (failures) return 1;
    puts("FE35_CLEANUP_CERTAINTY_C_CASES_OK=8");
    return 0;
}
