import React from 'react';
import Sparkline from 'react-sparkline';
import Classnames from 'classnames';

const sparkVals = Array(60).fill(0);
const sparkAverages = Array(60).fill(0);
let processedVals;

function toggle( props ) {
  const { status = {} } = props;
  props.comm.send({ 
      method: 'toggle', 
      data: { 
        action: status.running ? 'stop' : 'start' } 
      }, props.cell.get_callbacks() );
}

function sum( vals ) {
  return vals.reduce( function( a, b ) {
    return a + b;
  });
}

function DisplayStatus( props ) {
    const { status = {} } = props;
    const action = status.running ? 'Stop' : 'Start';
    const running = status.running ? 'Running' : 'Stopped';

    const statusClasses = Classnames(
      'machinestat-status', {
        'machinestat-status-running': status.running
      }
    );

    let processedPercent;
    let average = 0;
    let errPercent;
    let timeLeft;

    if ( typeof status.processed !== 'undefined' ) {
      //console.log(status.errored, status.processed, status.queue_size); 
      const totalProcessed = status.errored + status.processed;
      const totalQueued = totalProcessed + status.queue_size;
      
      processedPercent = ( totalProcessed / ( totalQueued + totalProcessed ) ) * 100;

      if ( !processedVals ) {
        processedVals = Array(10).fill( processedPercent );
      } else {
        processedVals.push( processedPercent );
        processedVals.shift();
      }

      average = sum( processedVals ) / processedVals.length;
      errPercent = ( Math.round(( status.errored / totalProcessed ) * 10 ) / 10 ) * 100 || null;
    
      // grow the sparkline
      sparkVals.push( status.processed );
      const windowSeconds = 10; 
      sparkAverages.push( sum( sparkVals.slice(Math.max(sparkVals.length - windowSeconds, 1)) ) / windowSeconds );

      const avgPerSecond = sum( sparkVals ) / sparkVals.length;
      timeLeft = (Math.round( status.queue_size / avgPerSecond ) * 100 ) / 100; 
    }


    return ( 
      <div>
        <div className="machinestat">
          <h5>Timbr Machine Status</h5>
          <div className={ statusClasses }>{ running }</div>
          <div className="machinestat-row">
            <div className="machinestat-performance">
              <div className="machinestat-label">Average per minute</div>
              <div className="machinestat-sparkline">
                <Sparkline width={200} height={25} data={ sparkAverages.slice(Math.max(sparkVals.length - 60, 1))} strokeWidth={'2px'} strokeColor={'#98c000'} />
              </div>
              <div className="machinestat-movedown">
                <a href="#" className='btn btn-primary' onClick={ () => toggle( props ) }>{ action }</a>
              </div>
            </div>
            <div className="machinestat-meta">
              <div className="machinestat-progress">
                <div className="machinestat-progress-key machinestat-label">
                  <ul>
                    <li className="key-queued">Queued</li>
                    <li className="key-processed">Processed</li>
                    <li className="key-average">Average</li>
                  </ul>
                </div>
                <div className="machinestat-progress-graph">
                  <div className="machinestat-progress-processed" style={{ width: `${processedPercent}%` }}></div>
                  <div className="machinestat-progress-average" style={{ left: `${average}%` }}></div>
                  <div className="machinestat-progress-label-processed">{ status.processed }</div>
                  <div className="machinestat-progress-label-queued">{ status.queue_size }</div>
                </div>
              </div>
              <div className="machinestat-movedown">
                { errPercent && `Errored: ${ status.errored } (${ errPercent }%)` } 
                &nbsp;
                { status.processed && timeLeft ? <span className="machinestat-indent">Est. Completion: { timeLeft } seconds</span> : '' }
              </div>
            </div>
          </div>
        </div>
      </div>
    );
}

export default DisplayStatus;
