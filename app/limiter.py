# app/limiter.py

LUA_SLIDING_WINDOW = """
local key = KEYS[1]
local current_time = tonumber(ARGV[1])
local window_size = tonumber(ARGV[2])
local max_requests = tonumber(ARGV[3])

local current_window = math.floor(current_time / window_size)
local prev_window = current_window - 1

local current_key = key .. ":" .. current_window
local prev_key = key .. ":" .. prev_window

local current_count = tonumber(redis.call('GET', current_key) or "0")
local prev_count = tonumber(redis.call('GET', prev_key) or "0")

local weight = 1 - ((current_time % window_size) / window_size)
local total_count = current_count + (prev_count * weight)

if total_count >= max_requests then
    -- Calculate how many seconds until the current window ends
    local time_passed_in_window = current_time % window_size
    local wait_time = window_size - time_passed_in_window
    return { -1, wait_time } -- Return a list: status -1 and the seconds to wait
else
    local new_count = redis.call('INCR', current_key)
    if new_count == 1 then
        redis.call('EXPIRE', current_key, window_size * 2)
    end
    return { 1, max_requests - total_count - 1 } -- Return status 1 and remaining tokens
end
"""