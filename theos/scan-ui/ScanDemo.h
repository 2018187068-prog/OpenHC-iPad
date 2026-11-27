#import <UIKit/UIKit.h>
#import <OpenHCBridge/OpenHCBridge.h>

@interface OHCScanDemoProvider : NSObject
+ (instancetype)syntheticDemoProvider;
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
@property(nonatomic, copy) void (^events)(NSArray<OHCBScanReceiverEvent *> *events);
#ifdef OPENHC_SCAN_UI_TEST
// Test-only access to synthetic callbacks. No production transport injection API.
@property(nonatomic, readonly) OHCBScanReceiverSession *session;
@property(nonatomic) BOOL automaticReady;
- (void)ready;
- (void)fail;
- (void)expire;
#endif
- (void)start;
- (void)stop;
@end

@interface OHCScanDemoController : UIViewController
@property(nonatomic, readonly) OHCScanDemoProvider *provider;
@property(nonatomic, readonly) UIImageView *qrView;
@property(nonatomic, readonly) UILabel *pinLabel;
@property(nonatomic, readonly) UILabel *statusLabel;
@property(nonatomic, readonly) UILabel *helperStatusLabel;
@property(nonatomic, readonly) UIButton *startButton;
@property(nonatomic, readonly) UIButton *stopButton;
@property(nonatomic, readonly) int64_t generation;
- (void)probeIndependentHelperWithCompletion:(void (^)(NSString *reply))completion;
#ifdef OPENHC_SCAN_UI_TEST
- (void)receive:(NSArray<OHCBScanReceiverEvent *> *)events;
#endif
- (void)invalidateForBackground;
@end

@interface OHCScanDemoDelegate : UIResponder <UIApplicationDelegate>
@property(nonatomic, strong) UIWindow *window;
@property(nonatomic, strong) OHCScanDemoController *controller;
@end
