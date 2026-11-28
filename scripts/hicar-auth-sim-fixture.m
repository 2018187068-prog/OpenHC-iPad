/* Test-only separately coded phone-side PAKE/identity-exchange algorithm. Derived
 * from OpenHC 8132399 TestSupport/TestPhone (Apache-2.0). This is not an
 * independent vendor implementation or evidence from an Honor phone.
 * Uses real crypto and actual socketpair bytes through the exported Native
 * bridge. Fixed phone material is visibly synthetic, never a deployment API. */
/*
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
#import <Foundation/Foundation.h>
#import <OpenHCBridge/OpenHCBridge.h>
#include "../native/crypto/openhc_crypto.h"
#include <fcntl.h>
#include <arpa/inet.h>
#include <poll.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>
/* Test-only raw-JSON relay to the host fake daemon. Four-byte length belongs
 * solely to this synthetic proxy, never to FE36 or the production adapter. */
static _Thread_local int transportPhoneFD=-1;
static _Thread_local int transportPhoneScenario=0;
static _Thread_local unsigned transportPhoneExchange=0;
static _Thread_local const char *transportPhonePhase="idle";
@interface OHCPhoneWireAction : NSObject
@property(nonatomic,copy) NSString *kind;
@property(nonatomic,strong) OHCBKotlinByteArray *bytes;
@end
@implementation OHCPhoneWireAction
@end
#define A(c,label) do { if(!(c)) { fprintf(stderr,"AUTH_FIXTURE_ASSERT=%s exchange=%u phase=%s\n",label,transportPhoneExchange,transportPhonePhase);fflush(stderr); @throw [NSException exceptionWithName:@"AuthFixture" reason:@"static assertion" userInfo:nil]; } } while(0)
static NSData *cat(NSData *a,NSData *b) { NSMutableData *d=[a mutableCopy];[d appendData:b];return d; }
static NSData *utf(NSString *s) { return [s dataUsingEncoding:NSUTF8StringEncoding]; }
static NSString *text(NSData *d) { return [[NSString alloc] initWithData:d encoding:NSUTF8StringEncoding]; }
static NSData *pattern(int n,int first) { NSMutableData *d=[NSMutableData dataWithLength:n];for(int i=0;i<n;i++)((uint8_t *)d.mutableBytes)[i]=(uint8_t)(i+first);return d; }
static NSString *hex(NSData *d) { NSMutableString *s=[NSMutableString string];const uint8_t *b=d.bytes;for(NSUInteger i=0;i<d.length;i++)[s appendFormat:@"%02X",b[i]];return s; }
static NSData *unhex(NSString *s) {
    A([s isKindOfClass:NSString.class]&&s.length%2==0&&s.length<=2048,"hex-shape");
    NSMutableData *d=[NSMutableData dataWithLength:s.length/2];
    for(NSUInteger i=0;i<d.length;i++) { unsigned v=0;NSScanner *scan=[NSScanner scannerWithString:[s substringWithRange:NSMakeRange(i*2,2)]];A([scan scanHexInt:&v]&&scan.isAtEnd,"hex-parse");((uint8_t *)d.mutableBytes)[i]=(uint8_t)v; }return d;
}
static NSDictionary *object(NSData *data) { id o=[NSJSONSerialization JSONObjectWithData:data options:0 error:NULL];A([o isKindOfClass:NSDictionary.class],"json-object");return o; }
static NSData *json(NSDictionary *o) { NSData *d=[NSJSONSerialization dataWithJSONObject:o options:0 error:NULL];A(d!=nil,"json-encode");return d; }
static BOOL integerEquals(id value,int expected) {
    return [value isKindOfClass:NSNumber.class] &&
        CFGetTypeID((__bridge CFTypeRef)value)!=CFBooleanGetTypeID() &&
        !CFNumberIsFloatType((__bridge CFNumberRef)value) && [value longLongValue]==expected;
}
static NSData *envelope(int op,NSString *data) { return json(@{@"oper_type":@(op),@"data":data,@"version":@"SYNTHETIC_PHONE_VERSION"}); }
static NSData *crypto(int op,NSData *key,NSData *a,NSData *b,NSData *c,int size) {
    static const uint8_t zero=0;NSMutableData *out=[NSMutableData dataWithLength:MAX(size,1)];
    A(oh_crypto(op,key.length?key.bytes:&zero,(int)key.length,a.length?a.bytes:&zero,(int)a.length,
        b.length?b.bytes:&zero,(int)b.length,c.length?c.bytes:&zero,(int)c.length,out.mutableBytes,size)==1,"real-crypto-operation");
    out.length=size;return out;
}
static NSData *sha(NSData *a) { return crypto(1,nil,a,nil,nil,32); }
static NSData *hmac(NSData *key,NSData *a) { return crypto(2,key,a,nil,nil,32); }
static NSData *hkdf(NSData *input,NSData *salt,NSString *info,int size) {
    A(size>0&&size<=32,"hkdf-one-block");uint8_t one=1;
    return [hmac(hmac(salt,input),cat(utf(info),[NSData dataWithBytes:&one length:1])) subdataWithRange:NSMakeRange(0,size)];
}
static NSData *modpow(NSData *base,NSData *exponent,NSData *prime) { return crypto(10,base,exponent,nil,prime,384); }
static OHCBKotlinByteArray *kb(NSData *data) { OHCBKotlinByteArray *b=[OHCBKotlinByteArray arrayWithSize:(int32_t)data.length];const uint8_t *p=data.bytes;for(int32_t i=0;i<b.size;i++)[b setIndex:i value:(int8_t)p[i]];return b; }
static NSData *nd(OHCBKotlinByteArray *b) { if(!b)return nil;NSMutableData *d=[NSMutableData dataWithLength:b.size];for(int32_t i=0;i<b.size;i++)((uint8_t *)d.mutableBytes)[i]=(uint8_t)[b getIndex:i];return d; }
static void transfer(int writer,int reader,const uint8_t *bytes,size_t n,uint8_t *out) {
    struct pollfd w={writer,POLLOUT,0};A(poll(&w,1,1000)==1,"socket-write-bound");A(write(writer,bytes,n)==(ssize_t)n,"socket-write");
    size_t offset=0;while(offset<n) { struct pollfd r={reader,POLLIN,0};A(poll(&r,1,1000)==1,"socket-read-bound");ssize_t got=read(reader,out+offset,n-offset);A(got>0,"socket-read");offset+=(size_t)got; }
}
/* Raw JSON bytes only, no invented wire header. Known byte counts belong to the
 * fixture, not to a deployed parser. Arbitrary fragments reach the real framer. */
static NSArray<OHCBFe36AuthAction *> *ingress(OHCBFe36AuthSessionBridge *bridge,OHCBScanReceiverEvent *e,NSData *data) {
    if(transportPhoneFD>=0) {
        transportPhoneExchange++;transportPhonePhase="request-write";
        fprintf(stderr,"AUTH_PHONE_PHASE exchange=%u phase=%s\n",transportPhoneExchange,transportPhonePhase);
        uint32_t n=htonl((uint32_t)data.length);
        A(data.length>0&&data.length<=4096,"transport-phone-request-bound");
        A(write(transportPhoneFD,&n,4)==4,"transport-phone-length-write");
        const uint8_t *p=data.bytes;size_t left=data.length;
        while(left) { ssize_t wrote=write(transportPhoneFD,p,left);A(wrote>0,"transport-phone-write");p+=wrote;left-=(size_t)wrote; }
        transportPhonePhase="reply-header";uint8_t header[4];size_t at=0;
        while(at<4) { ssize_t got=read(transportPhoneFD,header+at,4-at);A(got>0,"transport-phone-reply-header");at+=(size_t)got; }
        memcpy(&n,header,4);n=ntohl(n);A(n<=4096,"transport-phone-reply-bound");
        NSMutableArray *actions=[NSMutableArray array];
        if(!n) {
            for(NSString *kind in @[@"FAILED",@"CLOSE"]) { OHCPhoneWireAction *a=[OHCPhoneWireAction new];a.kind=kind;[actions addObject:a]; }
        } else {
            NSMutableData *reply=[NSMutableData dataWithLength:n];at=0;
            while(at<n) { ssize_t got=read(transportPhoneFD,(uint8_t *)reply.mutableBytes+at,n-at);A(got>0,"transport-phone-reply");at+=(size_t)got; }
            OHCPhoneWireAction *a=[OHCPhoneWireAction new];a.kind=@"SEND";a.bytes=kb(reply);[actions addObject:a];
            /* Reference local rejection sends INFORM before Failed. Preserve
             * that order rather than interpreting a nonempty reply as success. */
            transportPhonePhase="reply-classify";
            NSDictionary *outer=object(reply);
            if([outer[@"oper_type"] isEqual:@3]) {
                A(integerEquals(outer[@"oper_type"],3),"transport-auth-oper-type");
                A([outer[@"data"] isKindOfClass:NSString.class],"transport-auth-data-type");
                NSDictionary *inner=object(utf(outer[@"data"]));
                if([inner[@"message"] isEqual:@0x8080]) {
                    int expected=transportPhoneScenario==1?17:(transportPhoneScenario==2?29:0);
                    NSDictionary *payload=inner[@"payload"];
                    A(expected && integerEquals(inner[@"message"],0x8080) &&
                        [payload isKindOfClass:NSDictionary.class] &&
                        integerEquals(payload[@"errorCode"],expected),"transport-expected-inform-error");
                    for(NSString *kind in @[@"FAILED",@"CLOSE"]) {
                        OHCPhoneWireAction *terminal=[OHCPhoneWireAction new];terminal.kind=kind;[actions addObject:terminal];
                    }
                    fprintf(stderr,"AUTH_PHONE_INFORM exchange=%u terminal=SEND_FAILED_CLOSE\n",transportPhoneExchange);
                }
            }
        } transportPhonePhase="reply-complete";return (NSArray *)actions;
    }
    int fd[2];A(!socketpair(AF_UNIX,SOCK_STREAM,0,fd),"ingress-socketpair");
    NSMutableArray *events=[NSMutableArray array];
    @try { const uint8_t *p=data.bytes;for(NSUInteger offset=0;offset<data.length;) {
        size_t n=MIN((offset%17)+1,data.length-offset);uint8_t copy[17];transfer(fd[0],fd[1],p+offset,n,copy);
        [events addObjectsFromArray:[bridge receiveGeneration:e.generation connection:7 bytes:kb([NSData dataWithBytes:copy length:n]) nowMillis:12]];memset(copy,0,sizeof(copy));offset+=n;
    } } @finally { close(fd[0]);close(fd[1]); }return events;
}
static NSArray<NSData *> *sends(NSArray<OHCBFe36AuthAction *> *actions) {
    NSMutableArray *messages=[NSMutableArray array];
    for(OHCBFe36AuthAction *a in actions) if([a.kind isEqualToString:@"SEND"]) {
        NSData *d=nd(a.bytes);A(d.length<=4096,"egress-limit");int fd[2];A(!socketpair(AF_UNIX,SOCK_STREAM,0,fd),"egress-socketpair");
        NSMutableData *received=[NSMutableData dataWithLength:d.length];
        @try { transfer(fd[0],fd[1],d.bytes,d.length,received.mutableBytes); } @finally { close(fd[0]);close(fd[1]); }
        [messages addObject:received];
    }return messages;
}
static BOOL has(NSArray<OHCBFe36AuthAction *> *actions,NSString *kind) { for(OHCBFe36AuthAction *a in actions)if([a.kind isEqualToString:kind])return YES;return NO; }
static NSDictionary *payload(NSArray<OHCBFe36AuthAction *> *actions,int expected) {
    NSArray *messages=sends(actions);A(messages.count==1,"single-auth-reply");NSDictionary *outer=object(messages[0]);A([outer[@"oper_type"] intValue]==3,"auth-envelope-oper");
    NSDictionary *inner=object(utf(outer[@"data"]));A([inner[@"message"] intValue]==expected,"auth-message-code");return inner[@"payload"];
}
static void rejected(NSArray<OHCBFe36AuthAction *> *actions,OHCBInMemoryTrustStore *store,int expectedError) {
    A(!has(actions,@"AUTHENTICATED")&&has(actions,@"FAILED")&&has(actions,@"CLOSE"),"negative-auth-terminal");
    A(actions.count==3 && [actions[0].kind isEqualToString:@"SEND"] &&
        [actions[1].kind isEqualToString:@"FAILED"] && [actions[2].kind isEqualToString:@"CLOSE"],"negative-auth-action-order");
    NSDictionary *error=payload(actions,0x8080);
    A([error[@"errorCode"] isEqual:@(expectedError)],"negative-auth-reference-error");
    if(transportPhoneFD<0) A(store.snapshot.peers.count==0&&store.snapshot.identities.count==0,"failed-auth-no-commit");
}
static NSData *exchange(OHCBScanReceiverEvent *e,NSData *prime,int scenario) {
    OHCBAuthServiceIdentity *service=[[OHCBAuthServiceIdentity alloc] initWithPackageName:@"org.example.auth" serviceType:@"EXAMPLE"];
    OHCBFe36AuthConfig *config=[[OHCBFe36AuthConfig alloc] initWithService:service selfAuthId:@"SYNTHETIC_CAR" envelopeVersion:@"X_0@00000000000000" deviceInfo:@{@"model":@"SYNTHETIC"}];
    OHCBTrustStoreSnapshot *empty=[[OHCBTrustStoreSnapshot alloc] initWithIdentities:@[] peers:@[]];
    OHCBInMemoryTrustStore *store=[[OHCBInMemoryTrustStore alloc] initWithInitial:empty];
    OHCBFe36AuthSessionBridge *bridge=[[OHCBFe36AuthSessionBridge alloc] initWithConfig:config trust:store];
    if(transportPhoneFD<0) {
        A(has([bridge handoffEvent:e nowMillis:10 deadlineMillis:20000],@"OPEN_AUTH_CONNECTION"),"same-pin-handoff");
        A([bridge connectedGeneration:e.generation connection:7 nowMillis:11].count==0,"single-connection");
    }
    NSData *hello=envelope(1,text(json(@{@"deviceId":@"SYNTHETIC_PHONE",@"has_pin":@YES,@"usb_connection":@NO})));
    NSArray *initial=sends(ingress(bridge,e,hello));A(initial.count==1,"wireless-handshake-answer");NSDictionary *answer=object(initial[0]);
    A([answer[@"usb_connection"] isEqual:@NO]&&!answer[@"pin_code"],"wireless-pin-not-resent");
    NSArray *step=ingress(bridge,e,envelope(3,@"{\"message\":1,\"payload\":{\"version\":{\"currentVersion\":\"1.0.0\",\"minVersion\":\"1.0.0\"},\"support256mod\":true,\"operationCode\":1}}"));
    NSDictionary *p=payload(step,0x8001);NSData *salt=unhex(p[@"salt"]),*serverChallenge=unhex(p[@"challenge"]),*serverEpk=unhex(p[@"epk"]);
    A(salt.length==16&&serverChallenge.length==16&&serverEpk.length==384,"server-pake-shape");
    NSString *pin=e.pinCode;if(scenario==1)pin=[pin isEqualToString:@"000000"]?@"000001":@"000000";
    NSData *secret=hkdf(utf(pin),salt,@"hichain_speke_base_info",32),*two=pattern(1,2),*esk=pattern(32,1),*challenge=pattern(16,0x40);
    NSData *generator=modpow(secret,two,prime),*epk=modpow(generator,esk,prime),*shared=modpow(serverEpk,esk,prime);
    NSData *okm=hkdf(shared,salt,@"hichain_speke_sessionkey_info",32),*key=[okm subdataWithRange:NSMakeRange(0,16)];
    NSMutableData *proofKey=[NSMutableData dataWithLength:32];memcpy(proofKey.mutableBytes,(const uint8_t *)okm.bytes+16,16);
    NSData *proof=hmac(proofKey,cat(challenge,serverChallenge));
    step=ingress(bridge,e,envelope(3,text(json(@{@"message":@2,@"payload":@{@"kcfData":hex(proof),@"challenge":hex(challenge),@"epk":hex(epk)}}))));
    if(scenario==1) { rejected(step,store,17);A(![bridge takeSessionKeyGeneration:e.generation connection:7 nowMillis:13],"wrong-pin-no-key");return nil; }
    p=payload(step,0x8002);A([unhex(p[@"kcfData"]) isEqual:hmac(proofKey,cat(serverChallenge,challenge))],"verified-server-pake-proof");
    NSData *seed=pattern(32,0x80),*pk=crypto(5,seed,nil,nil,nil,32);
    NSString *phoneId=scenario==3?@"CHANGED_SYNTHETIC_PHONE":@"SYNTHETIC_PHONE";
    NSData *info=utf([NSString stringWithFormat:@"{\"authId\":\"%@\", \"authPk\":\"%@\"}",hex(utf(phoneId)),hex(pk)]);
    NSMutableData *signature=[crypto(6,seed,sha(cat(cat(challenge,serverChallenge),info)),nil,nil,64) mutableCopy];
    if(scenario==2)((uint8_t *)signature.mutableBytes)[0]^=1;
    NSData *nonce=pattern(12,0x60),*cipher=cat(nonce,crypto(3,key,nonce,utf(@"hichain_exchange_request"),cat(info,signature),(int)(info.length+signature.length+16)));
    step=ingress(bridge,e,envelope(3,text(json(@{@"message":@3,@"payload":@{@"exAuthInfo":hex(cipher)}}))));
    if(scenario==2||scenario==3) { rejected(step,store,29);return nil; }
    p=payload(step,0x8003);NSData *response=unhex(p[@"exAuthInfo"]);A(response.length>28,"exchange-response-size");
    NSData *plain=crypto(4,key,[response subdataWithRange:NSMakeRange(0,12)],utf(@"hichain_exchange_response"),[response subdataWithRange:NSMakeRange(12,response.length-12)],(int)response.length-28);
    A(plain.length>64,"exchange-plain-size");NSData *carInfo=[plain subdataWithRange:NSMakeRange(0,plain.length-64)],*carSig=[plain subdataWithRange:NSMakeRange(plain.length-64,64)];NSDictionary *car=object(carInfo);
    A([unhex(car[@"authId"]) isEqual:utf(@"SYNTHETIC_CAR")],"server-auth-id-bound");
    (void)crypto(7,unhex(car[@"authPk"]),sha(cat(cat(serverChallenge,challenge),carInfo)),carSig,nil,1);
    if(transportPhoneFD>=0) return hkdf(key,salt,@"hichain_return_key",16);
    A(has(step,@"AUTHENTICATED")&&!has(step,@"FAILED"),"real-pairing-success");
    A(store.snapshot.peers.count==1&&store.snapshot.identities.count==1,"verified-trust-committed");
    NSData *result=nd([bridge takeSessionKeyGeneration:e.generation connection:7 nowMillis:13]);
    A([result isEqual:hkdf(key,salt,@"hichain_return_key",16)],"real-same-session-key");
    A(![bridge takeSessionKeyGeneration:e.generation connection:7 nowMillis:13],"key-consumed-once");
    A([bridge handoffEvent:e nowMillis:13 deadlineMillis:20000].count==0,"handoff-consumed-once");
    return result;
}
static NSData *phonePrime(void) { return unhex(@"FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74020BBEA63B139B22514A08798E3404DDEF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7EDEE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F83655D23DCA3AD961C62F356208552BB9ED529077096966D670C354E4ABC9804F1746C08CA18217C32905E462E36CE3BE39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF6955817183995497CEA956AE515D2261898FA051015728E5A8AAAC42DAD33170D04507A33A85521ABDF1CBA64ECFB850458DBEF0A8AEA71575D060C7DB3970F85A6E1E4C7ABF5AE8CDB0933D71E8C94E04A25619DCEE3D2261AD2EE6BF12FFA06D98A0864D87602733EC86A64521F2B18177B200CBBE117577A615D6C770988C0BAD946E208E24FA074E5AB3143DB5BFCE0FD108E4B82D120A93AD2CAFFFFFFFFFFFFFFFF"); }
int openhc_fe36_auth_fixture(OHCBScanReceiverEvent *handoff) {
    @try {
        A([handoff.kind isEqualToString:@"AUTH_HANDOFF"]&&handoff.pinCode.length==6,"owner-auth-event");
        NSData *prime=phonePrime();
        for(int scenario=0;scenario<4;scenario++)exchange(handoff,prime,scenario);
        fprintf(stderr,"FE36_AUTH_OBJC_SOCKET_CASES_OK=4\n");return 0;
    } @catch(NSException *error) { (void)error;return 96; }
}

NSData *openhc_fe36_transport_phone(OHCBScanReceiverEvent *event,int fd,int scenario) {
    transportPhoneFD=fd;transportPhoneScenario=scenario;transportPhoneExchange=0;
    @try { NSData *key=exchange(event,phonePrime(),scenario);
        A(!scenario || key==nil,"negative-phone-no-key");return key;
    } @catch(NSException *error) {
        /* Only our static exception name/reason are safe to record. Framework
         * exception text may embed inputs, so replace it with fixed tokens. */
        BOOL known=[error.name isEqualToString:@"AuthFixture"];
        fprintf(stderr,"AUTH_PHONE_EXCEPTION name=%s reason=%s exchange=%u phase=%s\n",
            known?"AuthFixture":"redacted-external",known?"static-assertion":"redacted-external",
            transportPhoneExchange,transportPhonePhase);fflush(stderr);@throw;
    } @finally { transportPhoneFD=-1;transportPhoneScenario=0;transportPhonePhase="idle"; }
}
