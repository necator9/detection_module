#   statistic_log.py
#
#   The class provides data collection functionality for multi threading usage. All data stored in <filename>.db file
#   (by default - sen_info_0.db)
#   A frequency of sensors' polling does not influence on the class performance.
#
#   Input arguments:
#   args - array of names and queues for writing
#   stop - event for stop of the class
#   Optional: base_name = 'sen_info_0'
#
#   Important:
#   incoming array should be formatted as multidimensional array with 3 columns: table name, queue with data, names
#   of columns, split by "|" symbol.

#   Example:
#   in_ar = [["<sensor_1>", <queue_1>, "column_1|column_2"],
#           ["<sensor_2>", <queue_2>, "column_1|column_2"]]

#   Sample of the queue item has to contain such amount of elements as table's columns amount


#   Author: Ivan Matveev
#   E-mail: i.matveev@emw.hs-anhalt.de
#   Date: 17.11.2016


import threading
import Queue
import sqlite3 as lite
import os
import logging.config
import time
import copy
import logging

#logger = logging.getLogger(__name__)


logger = logging.getLogger('spam_application')
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)

logger.addHandler(ch)
class Statistic(threading.Thread):
    def __init__(self, stop, in_parameters, base_name='sen_info_0', buf_size=10000, commit_interval=60):
        threading.Thread.__init__(self, name="Main thread")

        self.in_parameters = copy.copy(in_parameters)
        self.buffered_qs = dict.fromkeys(self.in_parameters)
        for key in self.buffered_qs: self.buffered_qs[key] = Queue.Queue()

        self.commit_interval = commit_interval
        self.buf_size = buf_size

        self.stop_event = stop
        self.base_name = base_name

        self.internal_stop = threading.Event()
        self.internal_stop.set()

    def writer(self):
        logger.info("Started")
        conn = lite.connect(self.base_name)
        cur = conn.cursor()

        for name in self.in_parameters:
            cur.execute("CREATE TABLE %s (%s REAL)" % (name, self.in_parameters[name]["col_name"][0]))
            logger.debug("%s table created" % name)

            for x in range(len(self.in_parameters[name]["col_name"])):
                if x != 0:
                    cur.execute("ALTER TABLE %s ADD COLUMN %s REAL" % (name, self.in_parameters[name]["col_name"][x]))

        st_time = time.time()
        while self.internal_stop.isSet():
            for name in self.buffered_qs:
                try:
                    packet = self.buffered_qs[name].get(timeout=3)
                    print packet
                    packet = zip(*packet)
                    cur.executemany("INSERT INTO %s VALUES(%s)"
                                    % (name, ("?, " * len(self.buffered_qs[name]["col_name"]))[:-2]), packet)
                except Queue.Empty:
                    logger.debug("%s queue timeout" % self.buffered_qs[name])

            qs_counter = 0
            for name in self.buffered_qs:
                qs_counter += self.buffered_qs[name].qsize()

            if (time.time() - st_time) > self.commit_interval:
                st_time = time.time()
                conn.commit()
                logger.info("Commit performed")

            if not self.internal_stop.isSet() and qs_counter == 0: break

        conn.commit()
        conn.close()
        logger.info("Finished")

    def wrapper(self, in_q):
        temp = []
        while len(temp) < self.buf_size:
            try: temp.append(in_q.get(timeout=3))
            except Queue.Empty: return temp, False
        return temp, True

    def buffering(self, in_q, out_q):
        logger.info("Started")
        while True:
            packet, flag = self.wrapper(in_q)
            if not flag:
                logger.warning("Packet wrapper timeout")
                out_q.put(packet)
            if not self.stop_event.isSet() and in_q.qsize() == 0: break
        logger.debug("Items in queue rest  " + str(in_q.qsize()))
        logger.info("Finished")

    def check_on_file(self):
        logger.debug("Check file on existence")
        nm_b = 0
        while nm_b < 1000:
            self.base_name = 'sen_info_%s.db' % nm_b
            if os.path.exists(self.base_name):
                nm_b += 1
                logger.debug("File exists, number is incremented: <filename>_%s" % nm_b)
            else:
                logger.info("Database filename: %s" % self.base_name)
                break

    def run(self):
        logger.info("START")
        self.check_on_file()

        buf_threads = []
        for key in self.in_parameters:
            thr = threading.Thread(name='%s buffering thread' % key, target=self.buffering,
                                   args=(self.in_parameters[key]["queue"], self.buffered_qs[key]))
            thr.start()
            buf_threads.append(thr)

        wr = threading.Thread(name='Writer thread', target=self.writer)
        wr.start()

        while self.stop_event.is_set(): time.sleep(1)
        logger.info("Stop event received")

        for i in buf_threads: i.join()
        self.internal_stop.clear()
        logger.info("Internal event is cleared")
        wr.join()
        logger.warning("END")
