#import <Foundation/Foundation.h>

int openhc_cli_main(int argc, const char *argv[]);

int main(int argc, char *argv[]) {
    @autoreleasepool {
        int result = openhc_cli_main(argc, (const char **)argv);
        NSString *path = [NSHomeDirectory() stringByAppendingPathComponent:
            @"Documents/fe35-cli-result"];
        NSError *error = nil;
        NSString *directory = [path stringByDeletingLastPathComponent];
        if (![[NSFileManager defaultManager] createDirectoryAtPath:directory
                withIntermediateDirectories:YES attributes:nil error:&error]) return 90;
        error = nil;
        if (![[NSString stringWithFormat:@"%d\n", result] writeToFile:path
                atomically:YES encoding:NSUTF8StringEncoding error:&error]) return 90;
        return result;
    }
}
