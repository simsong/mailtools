#!/usr/bin/python

import os,email,mailbox,os.path,sys

indir=sys.argv[1]

if os.path.exists(sys.argv[2]):
    print sys.argv[2],"exists."
    exit(1)

out = open(sys.argv[2],"w")

if __name__=="__main__":
    for (dirpath,dirnames,filenames) in os.walk(indir):
        for filename in filenames:
            if filename.endswith(".emlx"):
                fn = dirpath+"/"+filename
                print fn
                msg = "\n".join(open(fn,"r").read().split("\n")[1:])
                em = email.message_from_string(msg)
                out.write(str(em))
                out.write("\n")
                    
                    
                
    
