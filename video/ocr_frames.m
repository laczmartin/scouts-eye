// Text recognition for video frames with Apple's Vision framework (macOS), used by video/check_sync.py.
// Objective-C rather than Swift: the Command Line Tools' Swift toolchain cannot import Vision on this machine
// (duplicate 'SwiftBridging' module map), clang can.
//
//     clang -fobjc-arc -O2 -framework Foundation -framework Vision -framework ImageIO -framework CoreGraphics \
//           video/ocr_frames.m -o video/raw/ocr_frames
//     video/raw/ocr_frames frame1.jpg frame2.jpg ...
//
// Prints one JSON object per image: {"path", "width", "height", "lines": [{"text", "conf", "x", "y", "w", "h"}]}
// with pixel boxes measured from the top-left corner. No network, nothing is stored.

#import <Foundation/Foundation.h>
#import <Vision/Vision.h>
#import <ImageIO/ImageIO.h>

static NSDictionary *recognise(NSString *path) {
    NSMutableArray *lines = [NSMutableArray array];
    NSURL *url = [NSURL fileURLWithPath:path];
    CGImageSourceRef src = CGImageSourceCreateWithURL((__bridge CFURLRef)url, NULL);
    CGImageRef img = src ? CGImageSourceCreateImageAtIndex(src, 0, NULL) : NULL;
    size_t W = img ? CGImageGetWidth(img) : 0, H = img ? CGImageGetHeight(img) : 0;
    if (img) {
        VNRecognizeTextRequest *req = [[VNRecognizeTextRequest alloc] init];
        req.recognitionLevel = VNRequestTextRecognitionLevelAccurate;
        req.usesLanguageCorrection = NO;          // names, minutes and numbers must stay as they are
        req.recognitionLanguages = @[@"en-US"];
        VNImageRequestHandler *h = [[VNImageRequestHandler alloc] initWithCGImage:img options:@{}];
        NSError *err = nil;
        [h performRequests:@[req] error:&err];
        for (VNRecognizedTextObservation *obs in req.results) {
            VNRecognizedText *best = [[obs topCandidates:1] firstObject];
            if (!best) continue;
            CGRect b = obs.boundingBox;            // normalised, origin bottom-left
            [lines addObject:@{@"text": best.string, @"conf": @(best.confidence),
                               @"x": @((int)(b.origin.x * W)), @"y": @((int)((1.0 - b.origin.y - b.size.height) * H)),
                               @"w": @((int)(b.size.width * W)), @"h": @((int)(b.size.height * H))}];
        }
        CGImageRelease(img);
    }
    if (src) CFRelease(src);
    return @{@"path": path, @"width": @(W), @"height": @(H), @"lines": lines};
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        for (int i = 1; i < argc; i++) {
            @autoreleasepool {
                NSDictionary *page = recognise([NSString stringWithUTF8String:argv[i]]);
                NSData *json = [NSJSONSerialization dataWithJSONObject:page options:0 error:nil];
                fwrite(json.bytes, 1, json.length, stdout);
                fputc('\n', stdout);
                fflush(stdout);
            }
        }
    }
    return 0;
}
