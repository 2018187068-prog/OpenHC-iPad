#import "ScanDemo.h"
#import "ScanQRCode.h"
#include <time.h>

static int64_t scanNow(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (int64_t)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}

@interface OHCScanDemoProvider ()
@property(nonatomic, strong) OHCBScanReceiverSession *session;
@property(nonatomic, strong) NSTimer *timer;
@end
@implementation OHCScanDemoProvider
- (instancetype)init {
    if ((self = [super init])) {
        OHCBHostIdentity *host = [[OHCBHostIdentity alloc] initWithModelId:@"A1B2C3"
            subModelId:@"D4" brand:@"Synthetic" deviceName:@"合成演示车机"];
        OHCBScanReceiverConfig *config = [[OHCBScanReceiverConfig alloc] initWithHost:host
            bluetoothAddress:@"A0:B1:C2:D3:E4:F5" supportsUsb:NO lifetimeMillis:60000];
        _session = [[OHCBScanReceiverSession alloc] initWithConfig:config];
        _automaticReady = YES;
    }
    return self;
}
- (void)emit:(NSArray<OHCBScanReceiverEvent *> *)events {
    NSAssert(NSThread.isMainThread, @"UI fake provider is serialized on main; no transport is linked");
    if (self.events) self.events(events);
    if ([self.session.state isEqualToString:@"STOPPED"] || [self.session.state isEqualToString:@"FAILED"])
        [self.timer invalidate];
}
- (void)start {
    [self emit:[self.session startNowMillis:scanNow()]];
    int64_t generation = self.session.generation;
    [self.timer invalidate];
    __weak typeof(self) weakSelf = self;
    self.timer = [NSTimer scheduledTimerWithTimeInterval:.1 repeats:YES block:^(NSTimer *timer) {
        OHCScanDemoProvider *owner = weakSelf;
        if (!owner) { [timer invalidate]; return; }
        [owner emit:[owner.session tickGeneration:generation nowMillis:scanNow()]];
    }];
    if (self.automaticReady) dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC),
        dispatch_get_main_queue(), ^{
            OHCScanDemoProvider *owner = weakSelf;
            if (owner.session.generation == generation) [owner ready];
        });
}
- (void)ready {
    int64_t generation = self.session.generation;
    [self emit:[self.session onControlRfcommReadyGeneration:generation channel:16 nowMillis:scanNow()]];
    [self emit:[self.session onControlSdpReadyGeneration:generation nowMillis:scanNow()]];
}
- (void)stop { [self emit:[self.session stopGeneration:self.session.generation]]; }
- (void)fail { [self emit:[self.session onControlFailureGeneration:self.session.generation nowMillis:scanNow()]]; }
- (void)expire {
    [self emit:[self.session tickGeneration:self.session.generation
        nowMillis:self.session.deadlineMillis.longLongValue]];
}
- (void)dealloc { [_timer invalidate]; }
@end

@interface OHCScanDemoController ()
@property(nonatomic, strong) OHCScanDemoProvider *provider;
@property(nonatomic, strong) UIImageView *qrView;
@property(nonatomic, strong) UILabel *pinLabel;
@property(nonatomic, strong) UILabel *statusLabel;
@property(nonatomic, strong) UIButton *startButton;
@property(nonatomic, strong) UIButton *stopButton;
@property(nonatomic) int64_t generation;
@property(nonatomic) BOOL accepting;
@property(nonatomic) BOOL foreground;
@property(nonatomic) NSUInteger readyCount;
@end
@implementation OHCScanDemoController
- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = UIColor.systemBackgroundColor;
    self.foreground = YES;
    UILabel *title = [UILabel new];
    title.text = @"OpenHC · 扫码演示";
    title.font = [UIFont preferredFontForTextStyle:UIFontTextStyleTitle1];
    UILabel *notice = [UILabel new];
    notice.text = @"合成演示 · 手机不可连接\n仅验证页面与二维码，不启动蓝牙或真实会话。";
    notice.numberOfLines = 0;
    notice.textColor = UIColor.secondaryLabelColor;
    self.statusLabel = [UILabel new];
    self.statusLabel.text = @"未开始";
    self.statusLabel.accessibilityIdentifier = @"scan.status";
    self.qrView = [UIImageView new];
    self.qrView.backgroundColor = UIColor.whiteColor;
    self.qrView.layer.magnificationFilter = kCAFilterNearest;
    self.qrView.layer.minificationFilter = kCAFilterNearest;
    self.qrView.contentMode = UIViewContentModeCenter;
    self.qrView.accessibilityIdentifier = @"scan.qr";
    self.pinLabel = [UILabel new];
    self.pinLabel.font = [UIFont monospacedDigitSystemFontOfSize:28 weight:UIFontWeightMedium];
    self.pinLabel.accessibilityIdentifier = @"scan.pin";
    self.startButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.startButton setTitle:@"Start · 开始演示" forState:UIControlStateNormal];
    [self.startButton addTarget:self action:@selector(startDemo) forControlEvents:UIControlEventTouchUpInside];
    self.stopButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.stopButton setTitle:@"Stop · 停止" forState:UIControlStateNormal];
    [self.stopButton addTarget:self action:@selector(stopDemo) forControlEvents:UIControlEventTouchUpInside];
    self.stopButton.enabled = NO;
    UIStackView *buttons = [[UIStackView alloc] initWithArrangedSubviews:@[self.startButton, self.stopButton]];
    buttons.axis = UILayoutConstraintAxisHorizontal;
    buttons.distribution = UIStackViewDistributionFillEqually;
    UIStackView *stack = [[UIStackView alloc] initWithArrangedSubviews:
        @[title, notice, self.statusLabel, self.qrView, self.pinLabel, buttons]];
    stack.axis = UILayoutConstraintAxisVertical;
    stack.spacing = 18;
    stack.alignment = UIStackViewAlignmentCenter;
    stack.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:stack];
    [NSLayoutConstraint activateConstraints:@[
        [stack.centerXAnchor constraintEqualToAnchor:self.view.centerXAnchor],
        [stack.centerYAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.centerYAnchor],
        [stack.widthAnchor constraintLessThanOrEqualToConstant:520],
        [stack.leadingAnchor constraintGreaterThanOrEqualToAnchor:self.view.safeAreaLayoutGuide.leadingAnchor constant:20],
        [stack.trailingAnchor constraintLessThanOrEqualToAnchor:self.view.safeAreaLayoutGuide.trailingAnchor constant:-20],
        [buttons.widthAnchor constraintEqualToAnchor:stack.widthAnchor],
        [self.qrView.widthAnchor constraintEqualToConstant:280],
        [self.qrView.heightAnchor constraintEqualToConstant:280]
    ]];
    self.provider = [OHCScanDemoProvider new];
    __weak typeof(self) weakSelf = self;
    self.provider.events = ^(NSArray *events) { [weakSelf receive:events]; };
    [self clearPairing];
}
- (void)clearPairing {
    self.qrView.image = nil;
    self.qrView.hidden = YES;
    self.pinLabel.text = nil;
    self.pinLabel.hidden = YES;
}
- (void)startDemo {
    if (self.accepting || !self.foreground) return;
    [self clearPairing];
    self.accepting = YES;
    self.generation = 0;
    self.readyCount = 0;
    self.statusLabel.text = @"准备合成会话…";
    self.startButton.enabled = NO;
    self.stopButton.enabled = YES;
    [self.provider start];
}
- (void)stopDemo {
    self.accepting = NO;
    [self clearPairing]; // synchronous, before provider cleanup/events
    self.startButton.enabled = self.foreground;
    self.stopButton.enabled = NO;
    self.statusLabel.text = @"已停止";
    [self.provider stop];
}
- (void)receive:(NSArray<OHCBScanReceiverEvent *> *)events {
    NSAssert(NSThread.isMainThread, @"UI events require main-thread delivery");
    for (OHCBScanReceiverEvent *event in events) {
        if (!self.accepting || !self.foreground) continue;
        if ([event.kind isEqualToString:@"OPEN_CONTROL_LISTENER"] && self.generation == 0)
            self.generation = event.generation;
        if (event.generation != self.generation) continue;
        if ([event.kind isEqualToString:@"PAIRING_READY"]) {
            if (self.readyCount++) continue;
            UIImage *qr = OHCScanQRCode(event.qrCode, 3, NULL);
            if (!qr || event.pinCode.length != 6) { [self stopDemo]; return; }
            self.qrView.image = qr;
            self.qrView.hidden = NO;
            self.pinLabel.text = event.pinCode;
            self.pinLabel.hidden = NO;
            self.statusLabel.text = @"合成码已就绪 · 不可连接";
        } else if ([event.kind isEqualToString:@"CLEAR_PAIRING"]) {
            [self clearPairing];
        } else if ([event.kind isEqualToString:@"FAILED"] || [event.kind isEqualToString:@"STOPPED"]) {
            [self clearPairing];
            self.accepting = NO;
            self.startButton.enabled = self.foreground;
            self.stopButton.enabled = NO;
            self.statusLabel.text = [event.kind isEqualToString:@"FAILED"] ? @"合成会话失败" : @"合成会话已到期或停止";
        }
    }
}
- (void)invalidateForBackground {
    self.foreground = NO;
    [self stopDemo];
}
- (void)resumeForeground { self.foreground = YES; self.startButton.enabled = YES; }
@end

#ifdef OPENHC_SCAN_UI_TEST
void OHCCheckScanUI(OHCScanDemoController *controller);
void OHCCheckScanBackground(OHCScanDemoController *controller);
#endif
@implementation OHCScanDemoDelegate
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options {
    (void)application; (void)options;
    self.window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
    self.controller = [OHCScanDemoController new];
    self.window.rootViewController = self.controller;
    [self.window makeKeyAndVisible];
#ifdef OPENHC_SCAN_UI_TEST
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC), dispatch_get_main_queue(), ^{
        OHCCheckScanUI(self.controller);
    });
#endif
    return YES;
}
- (void)applicationWillResignActive:(UIApplication *)application {
    (void)application;
    [self.controller invalidateForBackground];
#ifdef OPENHC_SCAN_UI_TEST
    OHCCheckScanBackground(self.controller);
#endif
}
- (void)applicationDidEnterBackground:(UIApplication *)application {
    (void)application;
    [self.controller invalidateForBackground];
}
- (void)applicationDidBecomeActive:(UIApplication *)application {
    (void)application;
    [self.controller resumeForeground];
}
@end
