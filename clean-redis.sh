redis-cli --scan --pattern 's2s:*' | xargs redis-cli del
redis-cli --scan --pattern 'tfr:*' | xargs redis-cli del