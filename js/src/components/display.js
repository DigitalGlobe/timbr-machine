import React from 'react';
import { Sparklines, SparklinesLine, SparklinesSpots } from 'react-sparklines';
import Classnames from 'classnames';
import autobind from 'autobind-decorator';
import dispatcher from './dispatcher';


@autobind
class DisplayStatus extends React.Component {

  constructor( props ) {
    super( props );
    this.state = {
      status: {},
      sparkVals: [],
      sparkAverages: [],
      processedVals: null,
      lastVal: null,
      sparkMax: '',
      sparkMin: '',
      sparkAvg: '',
      errPercent: null,
      errAverage: 0,
      processedPercent: 0,
      timeLeft: 0
    };
  }

  componentWillMount(){
    dispatcher.register( payload => {
      if ( payload.actionType === 'display_update' ) {
        this._update( payload.data );
      }
    });
  }

  _update( data ) {
    const state =  { ...this.state };
    const status = data.status;
    state.status = status;

    if ( typeof status.processed !== 'undefined' ) {
      const totalQueued = status.processed + status.queue_size;
      state.processedPercent = ( status.processed / totalQueued ) * 100;

      if ( !state.processedVals ) {
        state.processedVals = Array(10).fill( state.processedPercent );
      } else {
        state.processedVals.push( state.processedPercent );
        //state.processedVals.shift();
      }

      state.errAverage = this.sum( state.processedVals ) / state.processedVals.length;
      state.errPercent = ( Math.round(( status.errored / status.processed ) * 10 ) / 10 ) * 100 || null;

      // grow the sparkline
      if ( status.processed ) {
        if ( !state.lastVal ) {
          state.lastVal = status.processed;
        } else {
          state.sparkVals.push( status.processed - state.lastVal );
          state.lastVal = status.processed;

          if ( state.sparkVals.length > 1 ) {
            const windowSeconds = 10;
            const windowVals = state.sparkVals.slice(Math.max( state.sparkVals.length - windowSeconds, 1))
            state.sparkAverages.push( this.sum( windowVals ) / windowVals.length );

            if ( state.sparkAverages.length > 30 ) {
              state.sparkAverages.shift();
            }
        
            state.sparkMax = Math.ceil( Math.max.apply(null, state.sparkAverages) );
            state.sparkMin = Math.round( Math.min.apply(null, state.sparkAverages) );
            state.sparkAvg = Math.round( state.sparkAverages[ state.sparkAverages.length - 1 ] * 10 ) / 10;
            state.timeLeft = Math.ceil( ( status.queue_size /  ( this.sum( state.sparkAverages ) / state.sparkAverages.length ) ) ); //seconds
          }
        }
      }
    }
    this.setState({ ...state })
  }
  
  toggle() {
    const { status = {} } = this.state;
    this.props.comm.send({ 
      method: 'toggle', 
      data: { 
        action: status.running ? 'stop' : 'start' } 
      }, this.props.cell.get_callbacks() );
  }

  sum( vals ) {
    return vals.reduce( function( a, b ) {
      return a + b;
    });
  }

  render() {
    const { 
      sparkMax,
      sparkMin,
      sparkAvg,
      errPercent,
      errAverage,
      sparkAverages,
      processedPercent,
      timeLeft,
      status = {} 
    } = this.state;

    const action = status.running ? 'Stop' : 'Start';
    const running = status.running ? 'Running' : 'Stopped';

    const statusClasses = Classnames(
      'machinestat-status', {
        'machinestat-status-running': status.running
      }
    );

    return ( 
      <div>
        <div className="machinestat">
          <h5>Timbr Machine Status</h5>
          <div className={ statusClasses }>{ running }</div>
          <div className="machinestat-row">
            <div className="machinestat-performance">
              <div className="machinestat-label">Average per minute</div>
              <div className="machinestat-table">
                <div className="machinestat-cell machinestat-cell-tight">
                  <div className="machinestat-performance-high">{ sparkMax }</div>
                  <div className="machinestat-performance-low">{ sparkMin }</div>
                </div>
                <div className="machinestat-cell machinestat-cell-padded">
                  <div className="machinestat-sparkline">
                    <Sparklines data={sparkAverages} limit={30} width={175} height={25} margin={5}>
                      <SparklinesLine color="#98c000" style={{ strokeWidth: 1, stroke: "#98c000", fill: "none" }} />
                      <SparklinesSpots style={{ fill: "#98c000" }} />
                    </Sparklines>
                  </div>
                </div>
                <div className="machinestat-cell machinestat-cell-tight machinestat-cell-middle"><small>{ sparkAvg }</small></div>
              </div>

              <div className="machinestat-movedown">
                <a href="#" className='btn btn-primary' onClick={ this.toggle }>{ action }</a>
              </div>
            </div>
            <div className="machinestat-metastats">
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
                  <div className="machinestat-progress-average" style={{ left: `${errAverage}%` }}></div>
                  <div className="machinestat-progress-label-processed">{ status.processed }</div>
                  <div className="machinestat-progress-label-queued">{ status.queue_size }</div>
                </div>
              </div>
              <div className="machinestat-movedown">
                { status.errored > 0 && errPercent ? <span>Errored: { status.errored } <span className="machinestat-meta">({ errPercent }%)</span></span> : ''}
                &nbsp;
                { status.processed && timeLeft ? <span className="machinestat-indent">Est. Completion: { timeLeft } seconds</span> : ''}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }
}

export default DisplayStatus;
