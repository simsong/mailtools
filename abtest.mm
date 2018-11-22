/*
 * AddressBook test.
 */

#import <AddressBook/AddressBook.h>


#include <unistd.h>

NSUserDefaults *defaults=nil;
int debug=0;


int main(int argc,char **argv)
{

    int opt_v = 0;
    int ch;
    char *match = 0;
    while((ch = getopt(argc,argv,"vu:")) != -1){
	switch(ch){
	case 'v':
	    opt_v = 1;
	    break;
	case 'u':
	    match = optarg;
	    break;
	}
	
    }

    NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
    ABAddressBook *ab = [ABAddressBook sharedAddressBook];
    NSEnumerator *en= [[ab people] objectEnumerator];
    ABPerson *abp;

    while((abp = [en nextObject])){
	id email = [[abp valueForProperty:@"Email"] mutableCopy];
	
	//NSLog(@"\n\n******************** Read from AddressBook ******************");
	//NSLog(@"%@",abp);
	for(int i=0;i<[email count];i++){
	    NSString *name = [email labelAtIndex:i];
	    if([name isEqualToString:@"main"] ||
	       [name isEqualToString:@"Main"] ||
	       [name isEqualToString:@"_$!<Work>!$_"]){
		[email replaceLabelAtIndex:i withLabel:@"_$!<Work>!$_"];
		[abp setValue:email forProperty:@"Email"];
	    }
	}
    }
    [ab save];
}
