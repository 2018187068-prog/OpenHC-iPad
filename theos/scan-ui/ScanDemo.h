#import <UIKit/UIKit.h>
#import <OpenHCBridge/OpenHCBridge.h>

@interface OHCScanDemoProvider : NSObject
@property(nonatomic, copy) void (^events)(NSArray<OHCBScanReceiverEvent *> *events);
@property(nonatomic, readonly) OHCBScanReceiverSession *session;
@property(nonatomic) BOOL automaticReady;
- (void)start;
- (void)stop;
- (void)ready;
- (void)fail;
- (void)expire;
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
- (void)receive:(NSArray<OHCBScanReceiverEvent *> *)events;
- (void)invalidateForBackground;
@end

@interface OHCScanDemoDelegate : UIResponder <UIApplicationDelegate>
@property(nonatomic, strong) UIWindow *window;
@property(nonatomic, strong) OHCScanDemoController *controller;
@end
