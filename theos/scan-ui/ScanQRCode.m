#import "ScanQRCode.h"
#import <CoreImage/CoreImage.h>

UIImage *OHCScanQRCode(NSString *text, NSInteger scale, NSInteger *moduleWidth) {
    if (!text.length || scale < 1 || scale > 12) return nil;
    CIFilter *filter = [CIFilter filterWithName:@"CIQRCodeGenerator"];
    [filter setValue:[text dataUsingEncoding:NSUTF8StringEncoding] forKey:@"inputMessage"];
    [filter setValue:@"M" forKey:@"inputCorrectionLevel"];
    CIImage *matrix = filter.outputImage;
    if (!matrix || CGRectIsEmpty(matrix.extent)) return nil;
    size_t modules = (size_t)CGRectGetWidth(matrix.extent);
    if (modules > 177 || CGRectGetHeight(matrix.extent) != modules) return nil;
    if (moduleWidth) *moduleWidth = (NSInteger)modules;
    CIContext *ci = [CIContext contextWithOptions:@{kCIContextUseSoftwareRenderer: @YES}];
    CGImageRef code = [ci createCGImage:matrix fromRect:matrix.extent];
    if (!code) return nil;
    // Four white modules on each side; scale the modules by an integer only.
    size_t edge = (modules + 8) * (size_t)scale;
    CGColorSpaceRef colors = CGColorSpaceCreateDeviceRGB();
    CGContextRef bitmap = CGBitmapContextCreate(NULL, edge, edge, 8, edge * 4, colors,
        kCGImageAlphaPremultipliedLast | kCGBitmapByteOrder32Big);
    CGColorSpaceRelease(colors);
    if (!bitmap) { CGImageRelease(code); return nil; }
    CGContextSetRGBFillColor(bitmap, 1, 1, 1, 1);
    CGContextFillRect(bitmap, CGRectMake(0, 0, edge, edge));
    CGContextSetInterpolationQuality(bitmap, kCGInterpolationNone);
    CGContextDrawImage(bitmap, CGRectMake(4 * scale, 4 * scale, modules * scale, modules * scale), code);
    CGImageRef output = CGBitmapContextCreateImage(bitmap);
    UIImage *image = output ? [UIImage imageWithCGImage:output scale:1 orientation:UIImageOrientationUp] : nil;
    if (output) CGImageRelease(output);
    CGImageRelease(code);
    CGContextRelease(bitmap);
    return image;
}
