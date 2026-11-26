#import "ScanQRCode.h"
#import "ScanQRBitmap.h"
#include <stdlib.h>

static void releasePixels(void *info, const void *data, size_t size) {
    (void)info; (void)size;
    free((void *)data);
}

UIImage *OHCScanQRCode(NSString *text, NSInteger scale, NSInteger *moduleWidth) {
    if (moduleWidth) *moduleWidth = 0;
    if (!text.length || scale < 1 || scale > 12) return nil;
    NSData *utf8 = [text dataUsingEncoding:NSUTF8StringEncoding allowLossyConversion:NO];
    OHCScanQRBitmap bitmap;
    if (!OHCScanQRCreate(utf8.bytes, utf8.length, (int)scale, &bitmap)) return nil;
    CGDataProviderRef provider = CGDataProviderCreateWithData(NULL, bitmap.pixels,
        bitmap.edge * bitmap.edge, releasePixels);
    if (!provider) { free(bitmap.pixels); return nil; }
    CGColorSpaceRef colors = CGColorSpaceCreateDeviceGray();
    if (!colors) { CGDataProviderRelease(provider); return nil; }
    CGImageRef output = CGImageCreate(bitmap.edge, bitmap.edge, 8, 8, bitmap.edge,
        colors, kCGImageAlphaNone, provider, NULL, false, kCGRenderingIntentDefault);
    UIImage *image = output ? [UIImage imageWithCGImage:output scale:1 orientation:UIImageOrientationUp] : nil;
    if (image && moduleWidth) *moduleWidth = bitmap.modules;
    if (output) CGImageRelease(output);
    CGColorSpaceRelease(colors);
    CGDataProviderRelease(provider);
    return image;
}
