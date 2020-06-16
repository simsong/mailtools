MAILFILE:=$$HOME/"Google Drive/Summer 2020 Interns/Tuck_All_GMail.mbox"
tuck.pdf: Makefile graph.py
	python graph.py $(MAILFILE) > tuck.dot
	circo -Tpdf -o tuck.pdf tuck.dot
