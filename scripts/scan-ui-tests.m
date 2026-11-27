#import "../theos/scan-ui/ScanDemo.h"
#import "../theos/scan-ui/ScanQRCode.h"
#import <CoreImage/CoreImage.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static NSUInteger assertions;
static BOOL waitingForBackground;
@interface OHCDeferredHelperController : OHCScanDemoController
@property(nonatomic, copy) void (^pendingHelper)(NSString *reply);
@end
@implementation OHCDeferredHelperController
- (void)probeIndependentHelperWithCompletion:(void (^)(NSString *))completion {
    self.pendingHelper = completion;
}
@end
static void check(BOOL condition, const char *name) {
    assertions++;
    if (!condition) { fprintf(stderr, "SCAN_UI_FAILED=%s\n", name); exit(2); }
}
static NSString *documents(void) { return [NSHomeDirectory() stringByAppendingPathComponent:@"Documents"]; }
static void marker(NSString *name, NSString *value) {
    NSError *error = nil;
    [[NSFileManager defaultManager] createDirectoryAtPath:documents()
        withIntermediateDirectories:YES attributes:nil error:&error];
    check([value writeToFile:[documents() stringByAppendingPathComponent:name]
        atomically:YES encoding:NSUTF8StringEncoding error:&error], "write synthetic test result");
}
static void absent(OHCScanDemoController *c) {
    check(c.qrView.hidden && !c.qrView.image && c.pinLabel.hidden && !c.pinLabel.text.length,
        "pairing removed from UIKit image and label");
}
static void ready(OHCScanDemoController *c) {
    [c.startButton sendActionsForControlEvents:UIControlEventTouchUpInside];
    absent(c);
    [c.provider ready];
    check(!c.qrView.hidden && c.qrView.image && !c.pinLabel.hidden && c.pinLabel.text.length == 6,
        "ready visible in actual UIKit controls");
}
static void screenshot(OHCScanDemoController *c, NSString *name) {
    [c.view layoutIfNeeded];
    UIGraphicsImageRenderer *renderer = [[UIGraphicsImageRenderer alloc] initWithBounds:c.view.bounds];
    UIImage *image = [renderer imageWithActions:^(UIGraphicsImageRendererContext *context) {
        [c.view.layer renderInContext:context.CGContext];
    }];
    check([UIImagePNGRepresentation(image) writeToFile:[documents() stringByAppendingPathComponent:name]
        atomically:YES], "synthetic UI screenshot");
}
static void qrTests(void) {
    NSString *text = @"hicar://car/connect?devicename=合成演示车机&mac=A0:B1:C2:D3:E4:F5&moduleid=A1B2C3&submoduleid=D4&pin=000007&ability=4";
    for (NSNumber *factor in @[@2, @3, @4]) {
        NSInteger modules = 0;
        NSInteger scale = factor.integerValue;
        UIImage *image = OHCScanQRCode(text, scale, &modules);
        check(image && CGImageGetWidth(image.CGImage) == (modules + 8) * scale,
            "integer module scaling plus four-module quiet zone");
        size_t edge = CGImageGetWidth(image.CGImage);
        uint8_t *pixels = calloc(edge * edge, 4);
        CGColorSpaceRef space = CGColorSpaceCreateDeviceRGB();
        CGContextRef bitmap = CGBitmapContextCreate(pixels, edge, edge, 8, edge * 4, space,
            (CGBitmapInfo)kCGImageAlphaPremultipliedLast | kCGBitmapByteOrder32Big);
        CGContextDrawImage(bitmap, CGRectMake(0, 0, edge, edge), image.CGImage);
        BOOL crisp = YES, border = YES;
        for (size_t y = 0; y < edge; y++) for (size_t x = 0; x < edge; x++) {
            uint8_t *p = pixels + (y * edge + x) * 4;
            BOOL white = p[0] == 255 && p[1] == 255 && p[2] == 255;
            BOOL black = p[0] == 0 && p[1] == 0 && p[2] == 0;
            if (!white && !black) crisp = NO;
            if ((x < 4 * scale || y < 4 * scale || x >= edge - 4 * scale || y >= edge - 4 * scale) && !white)
                border = NO;
        }
        check(crisp && border, "binary pixels without interpolation and white quiet zone");
        CGContextRelease(bitmap); CGColorSpaceRelease(space); free(pixels);
        CIDetector *detector = [CIDetector detectorOfType:CIDetectorTypeQRCode
            context:nil options:@{CIDetectorAccuracy: CIDetectorAccuracyHigh}];
        NSArray *features = [detector featuresInImage:[CIImage imageWithCGImage:image.CGImage]];
        check(features.count == 1, "system QR detector finds one code");
        CIQRCodeFeature *feature = features.firstObject;
        check([feature.messageString isEqualToString:text], "UTF8 Chinese QR exact text and leading zero PIN");
        check([[feature.messageString dataUsingEncoding:NSUTF8StringEncoding]
            isEqualToData:[text dataUsingEncoding:NSUTF8StringEncoding]], "UTF8 byte equality");
    }
    check(!OHCScanQRCode(@"", 3, NULL) && !OHCScanQRCode(text, 0, NULL), "invalid render inputs fail closed");
    NSString *tooLong = [@"a" stringByPaddingToLength:1025 withString:@"a" startingAtIndex:0];
    check(!OHCScanQRCode(tooLong, 3, NULL) && !OHCScanQRCode(text, 13, NULL),
        "UTF8 byte and scale bounds fail closed");
    for (int repeat = 0; repeat < 20; repeat++) @autoreleasepool {
        check(OHCScanQRCode(text, 3, NULL) != nil, "repeated CPU QR generation retains image storage");
    }
    puts("SCAN_UI_CPU_QR_REPEAT_OK=20");
    puts("SCAN_UI_QR_UTF8_INTEGER_SCALE_CASES_OK=3");
}

static void helperIsolationTests(void) {
    OHCDeferredHelperController *c = [OHCDeferredHelperController new];
    [c loadViewIfNeeded];
    c.provider.automaticReady = NO;
    [c.startButton sendActionsForControlEvents:UIControlEventTouchUpInside];
    void (^oldReply)(NSString *) = c.pendingHelper;
    oldReply(@"PONG");
    absent(c); // PONG alone must never make a QR or mark either FE35 ready.
    check([c.provider.session.state isEqualToString:@"STARTING"], "PING is not FE35 readiness");
    [c.stopButton sendActionsForControlEvents:UIControlEventTouchUpInside];
    oldReply(@"PONG");
    check([c.helperStatusLabel.text isEqualToString:@"独立 helper：未探测"], "late PONG after Stop ignored");
    [c.startButton sendActionsForControlEvents:UIControlEventTouchUpInside];
    oldReply(@"PONG");
    check([c.helperStatusLabel.text isEqualToString:@"独立 helper：请求中…"], "old attempt cannot mark new helper request successful");
    c.pendingHelper(@"PONG");
    check([c.helperStatusLabel.text containsString:@"固定合成响应"], "current PONG remains explicitly synthetic");
    absent(c);
    void (^currentReply)(NSString *) = c.pendingHelper;
    [c invalidateForBackground];
    currentReply(@"PONG");
    check([c.helperStatusLabel.text isEqualToString:@"独立 helper：未探测"], "late background PONG ignored");
    absent(c);
    c.pendingHelper = nil;
    puts("SCAN_UI_CASE_OK=synthetic_helper_isolation");
}

void OHCCheckScanUI(OHCScanDemoController *c) {
    check(NSThread.isMainThread, "UI checks on main thread");
    c.provider.automaticReady = NO;
    absent(c);
    qrTests();
    helperIsolationTests();
    screenshot(c, @"scan-ui-idle.png");
    ready(c);
    screenshot(c, @"scan-ui-ready.png");
    NSArray *saved = [c.provider.session onControlSdpReadyGeneration:c.generation nowMillis:0];
    // A reversed-clock event is also a real common failure, and must clear UI.
    [c receive:saved];
    absent(c);
    puts("SCAN_UI_CASE_OK=failure_and_revocation");
    ready(c);
    [c.stopButton sendActionsForControlEvents:UIControlEventTouchUpInside];
    absent(c);
    [c.provider ready];
    absent(c);
    puts("SCAN_UI_CASE_OK=stop_and_late_ready");
    ready(c);
    [c.provider expire];
    absent(c);
    puts("SCAN_UI_CASE_OK=expiry");
    ready(c);
    [c.provider fail];
    absent(c);
    puts("SCAN_UI_CASE_OK=transport_failure");
    // Produce real pairing events from a separate common session, then deliver
    // them after our controller advanced to a new generation.
    OHCScanDemoProvider *old = [OHCScanDemoProvider syntheticDemoProvider];
    old.automaticReady = NO;
    __block NSArray *oldReady;
    old.events = ^(NSArray *events) {
        for (OHCBScanReceiverEvent *e in events)
            if ([e.kind isEqualToString:@"PAIRING_READY"]) oldReady = events;
    };
    [old start]; [old ready]; [old stop];
    check(oldReady.count == 1, "captured real old-generation pairing event");
    [c.startButton sendActionsForControlEvents:UIControlEventTouchUpInside];
    [c receive:oldReady]; absent(c);
    [c.provider ready];
    check(c.qrView.image != nil, "current generation remains ready");
    puts("SCAN_UI_CASE_OK=stale_generation");
    waitingForBackground = YES;
    marker(@"scan-ui-stage", @"READY_FOR_HOME\n");
}

void OHCCheckScanBackground(OHCScanDemoController *c) {
    if (!waitingForBackground) return;
    absent(c);
    [c.provider ready]; absent(c);
    check(!c.startButton.enabled && !c.stopButton.enabled, "background cannot start or retain pairing");
    screenshot(c, @"scan-ui-background.png");
    puts("SCAN_UI_CASE_OK=actual_application_background");
    printf("SCAN_UI_ASSERTIONS_OK=%lu\n", (unsigned long)assertions);
    fflush(stdout);
    marker(@"scan-ui-result", @"PASS\n");
    waitingForBackground = NO;
}
