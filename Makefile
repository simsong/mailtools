getdata:
	@echo Download some mailing lists data
	for year in 2010 2011 ; \
	do \
            for month in 01 02 03 04 05 06 07 08 09 10 11 12; \
            do \
	        list=lucene-java-user ;\
		mkdir -p mydata/$$list; \
	        fname=$$year$$month.mbox \
                out=mydata/$$list/$$fname ; \
	        echo $$out ;\
                if [ ! -r $out ]; then \
	           curl http://mail-archives.apache.org/mod_mbox/$$list/$$fname -o $$out ; fi ;\
            done \
        done

clean:
	rm -f *~
