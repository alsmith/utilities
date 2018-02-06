# utilities
Track utilities consumption

Create database with createDatabase.sql.

If you happen to have a table that stores average temperatures that
could help with predicting heating consumption, you could make the
necessary modifications in server.py where it wants to compute
'averageTemp', and of course set "enabled": true in config.json.

Works seamlessly if you happen to have a Buderus KM200 that you
collect data from (see https://github.com/alsmith/buderus).

Al Smith <ajs@aeschi.eu>
